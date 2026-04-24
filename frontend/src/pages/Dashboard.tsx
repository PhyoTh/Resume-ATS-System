import { useEffect, useMemo, useState } from 'react';
import {
    api,
    JDSummary,
    MATCH_TIERS,
    MatchTier,
    Resume,
    RESUME_STATUSES,
    ResumeStatus,
} from '../api';

const PAGE_SIZE = 50;

const TIER_BADGE: Record<MatchTier, string> = {
    Excellent: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    Good: 'bg-blue-100 text-blue-800 border-blue-200',
    Average: 'bg-amber-100 text-amber-800 border-amber-200',
    Bad: 'bg-rose-100 text-rose-800 border-rose-200',
};

function isRejected(r: Resume): boolean {
    return Boolean(r.is_rejected);
}

function rowStatus(r: Resume): string {
    if (r.processing_status === 'queued')
        return `Queued (${r.processing_step ?? 'Uploaded'})`;
    if (r.processing_status === 'processing')
        return r.processing_step ?? 'Processing';
    if (r.processing_status === 'error') return 'Failed';
    if (isRejected(r)) return 'Rejected document';
    return 'Ready';
}

export default function Dashboard() {
    const [jds, setJds] = useState<JDSummary[]>([]);
    const [selectedJdId, setSelectedJdId] = useState<number | null>(null);
    const [tierFilter, setTierFilter] = useState<MatchTier | ''>('');
    const [statusFilter, setStatusFilter] = useState<ResumeStatus | ''>('');
    const [resumes, setResumes] = useState<Resume[]>([]);
    const [total, setTotal] = useState(0);
    const [offset, setOffset] = useState(0);
    const [loading, setLoading] = useState(false);
    const [statusUpdating, setStatusUpdating] = useState<number | null>(null);

    useEffect(() => {
        api.listJDs()
            .then(setJds)
            .catch(() => setJds([]));
    }, []);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        api.listResumes({
            jdId: selectedJdId,
            tier: tierFilter || null,
            status: statusFilter || null,
            limit: PAGE_SIZE,
            offset,
        })
            .then((res) => {
                if (cancelled) return;
                setResumes(res.items);
                setTotal(res.total);
            })
            .catch(() => {
                if (cancelled) return;
                setResumes([]);
                setTotal(0);
            })
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, [selectedJdId, tierFilter, statusFilter, offset]);

    const resetOffset = () => setOffset(0);

    const onChangeJd = (value: string) => {
        setSelectedJdId(value === '' ? null : Number(value));
        resetOffset();
    };
    const onChangeTier = (value: string) => {
        setTierFilter(value as MatchTier | '');
        resetOffset();
    };
    const onChangeStatus = (value: string) => {
        setStatusFilter(value as ResumeStatus | '');
        resetOffset();
    };

    const onUpdateStatus = async (id: number, status: ResumeStatus) => {
        setStatusUpdating(id);
        try {
            const updated = await api.updateResumeStatus(id, status);
            setResumes((prev) =>
                prev.map((r) => (r.id === id ? updated : r)),
            );
        } finally {
            setStatusUpdating(null);
        }
    };

    const pageStart = total === 0 ? 0 : offset + 1;
    const pageEnd = Math.min(offset + PAGE_SIZE, total);
    const hasPrev = offset > 0;
    const hasNext = offset + PAGE_SIZE < total;

    const selectedJdLabel = useMemo(() => {
        if (selectedJdId == null) return 'All JDs';
        const jd = jds.find((j) => j.id === selectedJdId);
        return jd ? jd.title : `JD #${selectedJdId}`;
    }, [selectedJdId, jds]);

    return (
        <div className="space-y-5">
            <div className="flex items-baseline justify-between">
                <h1 className="text-2xl font-semibold">Candidates</h1>
                <span className="text-sm text-slate-500">
                    {total} total · ranking by score
                </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Filter label="Job description">
                    <select
                        className="select"
                        value={selectedJdId ?? ''}
                        onChange={(e) => onChangeJd(e.target.value)}
                    >
                        <option value="">All JDs</option>
                        {jds.map((jd) => (
                            <option key={jd.id} value={jd.id}>
                                {jd.title}
                            </option>
                        ))}
                    </select>
                </Filter>
                <Filter label="Match tier">
                    <select
                        className="select"
                        value={tierFilter}
                        onChange={(e) => onChangeTier(e.target.value)}
                    >
                        <option value="">All tiers</option>
                        {MATCH_TIERS.map((t) => (
                            <option key={t} value={t}>
                                {t}
                            </option>
                        ))}
                    </select>
                </Filter>
                <Filter label="Status">
                    <select
                        className="select"
                        value={statusFilter}
                        onChange={(e) => onChangeStatus(e.target.value)}
                    >
                        <option value="">All statuses</option>
                        {RESUME_STATUSES.map((s) => (
                            <option key={s} value={s}>
                                {s}
                            </option>
                        ))}
                    </select>
                </Filter>
            </div>

            <div className="text-xs text-slate-500">
                Match tier cut-offs: <Badge tier="Excellent" /> ≥ 90 ·{' '}
                <Badge tier="Good" /> 80–89 · <Badge tier="Average" /> 40–79 ·{' '}
                <Badge tier="Bad" /> &lt; 40
            </div>

            <table className="w-full border rounded bg-white overflow-hidden">
                <thead className="text-xs text-slate-500 bg-slate-50 uppercase tracking-wide">
                    <tr>
                        <th className="text-left px-4 py-2">Rank</th>
                        <th className="text-left px-4 py-2">Name</th>
                        <th className="text-left px-4 py-2">Email</th>
                        <th className="text-left px-4 py-2">YOE</th>
                        <th className="text-left px-4 py-2">Top skills</th>
                        <th className="text-left px-4 py-2">Tier</th>
                        <th className="text-left px-4 py-2">Score</th>
                        <th className="text-left px-4 py-2">Pipeline</th>
                        <th className="text-left px-4 py-2">Source</th>
                        <th className="text-left px-4 py-2"></th>
                    </tr>
                </thead>
                <tbody>
                    {resumes.map((r, i) => (
                        <tr
                            key={r.id}
                            className={
                                'border-t text-sm ' +
                                (isRejected(r) ? 'bg-red-50/40' : '')
                            }
                        >
                            <td className="px-4 py-2 text-slate-400">
                                {offset + i + 1}
                            </td>
                            <td className="px-4 py-2">
                                {r.extraction?.contact?.name ?? '—'}
                            </td>
                            <td className="px-4 py-2 font-mono text-xs">
                                {r.extraction?.contact?.email ?? '—'}
                            </td>
                            <td className="px-4 py-2">
                                {r.extraction?.calculated_yoe ?? '—'}
                            </td>
                            <td className="px-4 py-2 text-xs">
                                {(r.extraction?.technical_skills ?? [])
                                    .slice(0, 5)
                                    .join(', ')}
                            </td>
                            <td className="px-4 py-2">
                                {r.match_tier ? (
                                    <Badge tier={r.match_tier} />
                                ) : (
                                    <span className="text-slate-400 text-xs">
                                        —
                                    </span>
                                )}
                            </td>
                            <td className="px-4 py-2 font-semibold">
                                {!isRejected(r) && r.score != null
                                    ? Math.round(r.score)
                                    : '—'}
                                <div className="text-[10px] text-slate-400 mt-0.5">
                                    {rowStatus(r)}
                                </div>
                            </td>
                            <td className="px-4 py-2">
                                <select
                                    className="select text-xs"
                                    value={r.status}
                                    disabled={statusUpdating === r.id}
                                    onChange={(e) =>
                                        onUpdateStatus(
                                            r.id,
                                            e.target.value as ResumeStatus,
                                        )
                                    }
                                >
                                    {RESUME_STATUSES.map((s) => (
                                        <option key={s} value={s}>
                                            {s}
                                        </option>
                                    ))}
                                </select>
                            </td>
                            <td className="px-4 py-2 text-xs">
                                {jdLabelFor(r, jds)}
                            </td>
                            <td className="px-4 py-2">
                                <a
                                    href={api.resumeFileUrl(r.id)}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-blue-600 hover:underline text-sm"
                                >
                                    View Resume
                                </a>
                            </td>
                        </tr>
                    ))}
                    {!loading && resumes.length === 0 && (
                        <tr>
                            <td
                                colSpan={10}
                                className="px-4 py-6 text-center text-slate-400"
                            >
                                No candidates match the current filters.
                            </td>
                        </tr>
                    )}
                    {loading && resumes.length === 0 && (
                        <tr>
                            <td
                                colSpan={10}
                                className="px-4 py-6 text-center text-slate-400"
                            >
                                Loading…
                            </td>
                        </tr>
                    )}
                </tbody>
            </table>

            <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500">
                    {total === 0
                        ? 'No results'
                        : `Showing ${pageStart}–${pageEnd} of ${total} for ${selectedJdLabel}${
                              tierFilter ? ` · ${tierFilter}` : ''
                          }${statusFilter ? ` · ${statusFilter}` : ''}`}
                </span>
                <div className="flex gap-3">
                    <button
                        className="px-3 py-1.5 border rounded disabled:opacity-40"
                        disabled={!hasPrev || loading}
                        onClick={() =>
                            setOffset(Math.max(0, offset - PAGE_SIZE))
                        }
                    >
                        ← Previous {PAGE_SIZE}
                    </button>
                    <button
                        className="px-3 py-1.5 border rounded disabled:opacity-40"
                        disabled={!hasNext || loading}
                        onClick={() => setOffset(offset + PAGE_SIZE)}
                    >
                        Next {PAGE_SIZE} →
                    </button>
                </div>
            </div>

            <style>{`.select { display:block; width:100%; border:1px solid #e2e8f0; border-radius:6px; padding: 6px 10px; font-size: 14px; background: white; }`}</style>
        </div>
    );
}

function Filter({
    label,
    children,
}: {
    label: string;
    children: React.ReactNode;
}) {
    return (
        <label className="block">
            <span className="block text-xs uppercase tracking-wide text-slate-500 mb-1">
                {label}
            </span>
            {children}
        </label>
    );
}

function Badge({ tier }: { tier: MatchTier }) {
    return (
        <span
            className={`inline-block text-[11px] font-medium uppercase tracking-wide rounded px-2 py-0.5 border ${TIER_BADGE[tier]}`}
        >
            {tier}
        </span>
    );
}

function jdLabelFor(r: Resume, jds: JDSummary[]): string {
    if (r.scored_against_jd_id == null) return 'no JD';
    const jd = jds.find((j) => j.id === r.scored_against_jd_id);
    return jd ? jd.title : `JD #${r.scored_against_jd_id}`;
}
