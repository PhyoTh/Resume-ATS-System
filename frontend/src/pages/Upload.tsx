import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, JDSummary, Resume } from '../api';

type Status = 'queued' | 'processing' | 'done' | 'error';
interface Row {
    file: File;
    status: Status;
    step: string;
    taskId?: string;
    resumeId?: number;
    resume?: Resume;
    error?: string;
}

const POLL_INTERVAL_MS = 1200;
const POLL_MAX_ATTEMPTS = 240;

function delay(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRejected(resume: Resume | undefined): boolean {
    if (!resume) return false;
    return Boolean(resume.is_rejected);
}

export default function Upload() {
    const [rows, setRows] = useState<Row[]>([]);
    const [history, setHistory] = useState<Resume[]>([]);
    const [jds, setJds] = useState<JDSummary[]>([]);
    const [selectedJdId, setSelectedJdId] = useState<number | null>(null);
    const nav = useNavigate();

    useEffect(() => {
        api.listResumes({ limit: 20 })
            .then((res) => setHistory(res.items))
            .catch(() => setHistory([]));
        api.listJDs()
            .then((rows) => setJds(rows))
            .catch(() => setJds([]));
    }, []);

    const onFiles = (files: FileList | null) => {
        if (!files) return;
        const next: Row[] = Array.from(files).map((file) => ({
            file,
            status: 'queued',
            step: 'Uploaded',
        }));
        setRows((prev) => [...prev, ...next]);
        void runUploads(next, selectedJdId ?? undefined);
    };

    const pollTask = async (taskId: string, row: Row) => {
        for (let i = 0; i < POLL_MAX_ATTEMPTS; i += 1) {
            const task = await api.getResumeTask(taskId);
            setRows((prev) =>
                prev.map((r) =>
                    r.file === row.file
                        ? {
                              ...r,
                              status: task.status,
                              step: task.step,
                              error: task.error ?? undefined,
                              resumeId: task.resume_id,
                              resume: task.resume ?? r.resume,
                          }
                        : r,
                ),
            );

            if (task.resume) {
                setHistory((prev) => [
                    task.resume!,
                    ...prev.filter((p) => p.id !== task.resume!.id),
                ]);
            }

            if (task.status === 'done' || task.status === 'error') {
                return;
            }
            await delay(POLL_INTERVAL_MS);
        }

        setRows((prev) =>
            prev.map((r) =>
                r.file === row.file
                    ? {
                          ...r,
                          status: 'error',
                          error: 'Timed out while waiting for processing.',
                      }
                    : r,
            ),
        );
    };

    const runUploads = async (queue: Row[], jdId?: number) => {
        for (const row of queue) {
            try {
                const accepted = await api.uploadResume(row.file, jdId);
                setRows((prev) =>
                    prev.map((r) =>
                        r.file === row.file
                            ? {
                                  ...r,
                                  status: accepted.status,
                                  step: accepted.step,
                                  taskId: accepted.task_id,
                                  resumeId: accepted.resume_id,
                              }
                            : r,
                    ),
                );
                await pollTask(accepted.task_id, row);
            } catch (e) {
                setRows((prev) =>
                    prev.map((r) =>
                        r.file === row.file
                            ? { ...r, status: 'error', error: String(e) }
                            : r,
                    ),
                );
            }
        }
    };

    const queuedResumeIds = useMemo(() => {
        const ids = new Set<number>();
        for (const row of rows) {
            if (row.resume?.id != null) ids.add(row.resume.id);
        }
        return ids;
    }, [rows]);

    const persistedRows = useMemo(
        () => history.filter((r) => !queuedResumeIds.has(r.id)).slice(0, 20),
        [history, queuedResumeIds],
    );

    const retryResume = async (id: number, label: string) => {
        try {
            const accepted = await api.retryExtraction(id);
            // Splice a synthetic row into the queue so the user sees live
            // progress. `file` is a fake sentinel; pollTask keys on it.
            const sentinel = new File([], label);
            const newRow: Row = {
                file: sentinel,
                status: accepted.status,
                step: accepted.step,
                taskId: accepted.task_id,
                resumeId: accepted.resume_id,
            };
            setRows((prev) => [...prev, newRow]);
            // Remove the stale persisted entry so we don't render duplicates.
            setHistory((prev) => prev.filter((r) => r.id !== id));
            await pollTask(accepted.task_id, newRow);
        } catch (e) {
            alert(`Retry failed: ${e}`);
        }
    };

    const removeResume = async (id: number, label: string) => {
        if (!confirm(`Delete ${label}? This can't be undone.`)) return;
        try {
            await api.deleteResume(id);
        } catch (e) {
            alert(`Delete failed: ${e}`);
            return;
        }
        setHistory((prev) => prev.filter((r) => r.id !== id));
        setRows((prev) => prev.filter((r) => r.resumeId !== id));
    };

    const rejectedCount = useMemo(() => {
        const queueIds = new Set<number>();
        let n = 0;
        for (const r of rows) {
            if (r.resume?.id != null && isRejected(r.resume)) {
                queueIds.add(r.resume.id);
                n += 1;
            }
        }
        for (const r of history) {
            if (queueIds.has(r.id)) continue;
            if (isRejected(r)) n += 1;
        }
        return n;
    }, [rows, history]);

    const purgeRejected = async () => {
        if (rejectedCount === 0) return;
        const ok = confirm(
            `Delete all ${rejectedCount} resume${
                rejectedCount === 1 ? '' : 's'
            } that the LLM classified as NOT a resume? This can't be undone.`,
        );
        if (!ok) return;
        try {
            const res = await api.deleteRejectedResumes();
            setHistory((prev) => prev.filter((r) => !isRejected(r)));
            setRows((prev) =>
                prev.filter((r) => !(r.resume && isRejected(r.resume))),
            );
            alert(
                `Deleted ${res.deleted} non-resume row${
                    res.deleted === 1 ? '' : 's'
                }.`,
            );
        } catch (e) {
            alert(`Bulk delete failed: ${e}`);
        }
    };

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-semibold">Upload resumes</h1>

            <div className="rounded border bg-white p-4 space-y-2">
                <label className="block text-sm font-medium text-slate-700">
                    Upload these resumes to:
                </label>
                <select
                    className="border rounded px-3 py-2 text-sm w-full md:w-[380px]"
                    value={selectedJdId ?? ''}
                    onChange={(e) =>
                        setSelectedJdId(
                            e.target.value === ''
                                ? null
                                : Number(e.target.value),
                        )
                    }
                >
                    <option value="">
                        No job selected — parse only (no scoring)
                    </option>
                    {jds.map((jd) => (
                        <option key={jd.id} value={jd.id}>
                            {jd.title}
                        </option>
                    ))}
                </select>
                <p className="text-xs text-slate-500">
                    Pick a JD to score the candidate against. Leave it blank
                    to just parse the resume without scoring.
                </p>
            </div>

            <DropZone onFiles={onFiles} />


            <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-slate-500">
                    Uploaded resumes are saved to your local recruiter
                    database. Recent ones are listed below for quick access.
                </p>
                {rejectedCount > 0 && (
                    <button
                        onClick={purgeRejected}
                        className="text-sm text-red-700 border border-red-300 hover:bg-red-50 rounded px-3 py-1.5 whitespace-nowrap"
                    >
                        Delete {rejectedCount} non-resume{rejectedCount === 1 ? '' : 's'}
                    </button>
                )}
            </div>

            {(rows.length > 0 || persistedRows.length > 0) && (
                <table className="w-full border rounded bg-white overflow-hidden">
                    <thead className="text-sm text-slate-500 bg-slate-50">
                        <tr>
                            <th className="text-left px-4 py-2">File</th>
                            <th className="text-left px-4 py-2">Status</th>
                            <th className="text-left px-4 py-2">Candidate</th>
                            <th className="text-left px-4 py-2">Score</th>
                            <th className="text-left px-4 py-2"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r, i) => (
                            <tr
                                key={`queue-${i}`}
                                className={
                                    'border-t ' +
                                    (isRejected(r.resume)
                                        ? 'bg-red-50/40'
                                        : 'bg-white')
                                }
                            >
                                <td className="px-4 py-2 font-mono text-sm">
                                    {r.file.name}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    {r.status === 'queued' && (
                                        <span className="text-slate-600">
                                            queued ({r.step})
                                        </span>
                                    )}
                                    {r.status === 'processing' && (
                                        <span className="text-blue-600">
                                            {r.step}…
                                        </span>
                                    )}
                                    {r.status === 'done' &&
                                        !isRejected(r.resume) && (
                                            <span className="text-green-600">
                                                done
                                            </span>
                                        )}
                                    {r.status === 'done' &&
                                        isRejected(r.resume) && (
                                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide bg-red-100 text-red-800 border border-red-200 rounded px-1.5 py-0.5">
                                                Not a resume
                                            </span>
                                        )}
                                    {r.status === 'error' && (
                                        <span
                                            className="text-red-600"
                                            title={r.error}
                                        >
                                            error
                                        </span>
                                    )}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    {r.resume?.extraction?.contact?.name ??
                                        (r.status === 'error'
                                            ? '—'
                                            : 'Processing')}
                                    {isRejected(r.resume) && (
                                        <div className="text-xs text-red-700 mt-1">
                                            {r.resume?.rejection_reason ??
                                                'This document does not appear to be a valid resume.'}
                                        </div>
                                    )}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    {!isRejected(r.resume) &&
                                    r.resume?.score != null
                                        ? Math.round(r.resume.score)
                                        : '—'}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    {r.resume && (
                                        <div className="flex gap-3">
                                            <button
                                                className="text-blue-600 hover:underline"
                                                onClick={() =>
                                                    nav(
                                                        `/resumes/${r.resume!.id}`,
                                                    )
                                                }
                                            >
                                                Verify
                                            </button>
                                            {r.status === 'error' && (
                                                <button
                                                    className="text-amber-700 hover:underline"
                                                    onClick={() =>
                                                        retryResume(
                                                            r.resume!.id,
                                                            r.file.name,
                                                        )
                                                    }
                                                >
                                                    Retry
                                                </button>
                                            )}
                                            <button
                                                className="text-red-600 hover:underline"
                                                onClick={() =>
                                                    removeResume(
                                                        r.resume!.id,
                                                        r.file.name,
                                                    )
                                                }
                                            >
                                                Delete
                                            </button>
                                        </div>
                                    )}
                                </td>
                            </tr>
                        ))}

                        {persistedRows.map((r) => (
                            <tr
                                key={`persisted-${r.id}`}
                                className={
                                    'border-t ' +
                                    (isRejected(r)
                                        ? 'bg-red-50/40'
                                        : 'bg-slate-50/40')
                                }
                            >
                                <td className="px-4 py-2 font-mono text-sm">
                                    {r.filename}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    {r.processing_status === 'queued' && (
                                        <span className="text-slate-600">
                                            queued (
                                            {r.processing_step ?? 'Uploaded'})
                                        </span>
                                    )}
                                    {r.processing_status === 'processing' && (
                                        <span className="text-blue-600">
                                            {r.processing_step ?? 'processing'}…
                                        </span>
                                    )}
                                    {r.processing_status === 'error' && (
                                        <span
                                            className="text-red-600"
                                            title={r.processing_error ?? ''}
                                        >
                                            failed
                                        </span>
                                    )}
                                    {(r.processing_status === 'done' ||
                                        r.processing_status == null) &&
                                        !isRejected(r) && (
                                            <span className="text-emerald-600">
                                                saved
                                            </span>
                                        )}
                                    {(r.processing_status === 'done' ||
                                        r.processing_status == null) &&
                                        isRejected(r) && (
                                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide bg-red-100 text-red-800 border border-red-200 rounded px-1.5 py-0.5">
                                                Not a resume
                                            </span>
                                        )}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    {r.extraction?.contact?.name ?? '—'}
                                    {isRejected(r) && (
                                        <div className="text-xs text-red-700 mt-1">
                                            {r.rejection_reason ??
                                                'This document does not appear to be a valid resume.'}
                                        </div>
                                    )}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    {!isRejected(r) && r.score != null
                                        ? Math.round(r.score)
                                        : '—'}
                                </td>
                                <td className="px-4 py-2 text-sm">
                                    <div className="flex gap-3">
                                        <button
                                            className="text-blue-600 hover:underline"
                                            onClick={() =>
                                                nav(`/resumes/${r.id}`)
                                            }
                                        >
                                            Verify
                                        </button>
                                        {r.processing_status === 'error' && (
                                            <button
                                                className="text-amber-700 hover:underline"
                                                onClick={() =>
                                                    retryResume(
                                                        r.id,
                                                        r.filename,
                                                    )
                                                }
                                            >
                                                Retry
                                            </button>
                                        )}
                                        <button
                                            className="text-red-600 hover:underline"
                                            onClick={() =>
                                                removeResume(r.id, r.filename)
                                            }
                                        >
                                            Delete
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

function DropZone({ onFiles }: { onFiles: (files: FileList | null) => void }) {
    const [dragging, setDragging] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    const onDragEnter = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer?.types?.includes('Files')) setDragging(true);
    };
    const onDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        // Required so drop fires; setting dropEffect tells the OS we accept it.
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    };
    const onDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        // Only clear when actually leaving the zone (not crossing children).
        if (e.currentTarget === e.target) setDragging(false);
    };
    const onDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragging(false);
        const files = e.dataTransfer?.files ?? null;
        onFiles(files);
    };

    return (
        <div
            onClick={() => inputRef.current?.click()}
            onDragEnter={onDragEnter}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={
                'block border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ' +
                (dragging
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-300 bg-white hover:bg-slate-50')
            }
        >
            <input
                ref={inputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.png,.jpg,.jpeg"
                className="hidden"
                onChange={(e) => onFiles(e.target.files)}
            />
            <div className="text-slate-600 pointer-events-none">
                <span className="text-lg">
                    {dragging
                        ? 'Release to upload'
                        : 'Drop files here or click to select'}
                </span>
                <div className="text-sm text-slate-400 mt-1">
                    PDF, DOCX, PNG, JPG
                </div>
            </div>
        </div>
    );
}
