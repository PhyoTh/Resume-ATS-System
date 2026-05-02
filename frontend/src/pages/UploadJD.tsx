import { useEffect, useState } from 'react';
import { api, CustomField, JD, JDSummary } from '../api';

const BLANK_FORM = { id: null as number | null, title: '', body: '', skills: '' };

const FIELD_TYPES: CustomField['type'][] = ['text', 'bool', 'list', 'number'];

function formatDate(value: string | null): string {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString();
}

export default function UploadJD() {
    const [list, setList] = useState<JDSummary[]>([]);
    const [form, setForm] = useState(BLANK_FORM);
    const [saving, setSaving] = useState(false);

    const refresh = async () => {
        const rows = await api.listJDs();
        setList(rows);
        return rows;
    };

    useEffect(() => {
        refresh().catch(() => setList([]));
    }, []);

    const loadForEdit = async (id: number) => {
        const jd = await api.getJD(id);
        setForm({
            id: jd.id,
            title: jd.title,
            body: jd.body_md,
            skills: jd.required_skills.join(', '),
        });
    };

    const startNew = () => setForm(BLANK_FORM);

    const save = async () => {
        const required_skills = form.skills
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);
        const payload = {
            title: form.title,
            body_md: form.body,
            required_skills,
        };
        setSaving(true);
        try {
            let saved: JD;
            if (form.id == null) {
                saved = await api.createJD(payload);
            } else {
                saved = await api.updateJD(form.id, payload);
            }
            setForm({
                id: saved.id,
                title: saved.title,
                body: saved.body_md,
                skills: saved.required_skills.join(', '),
            });
            await refresh();
        } finally {
            setSaving(false);
        }
    };

    const remove = async (id: number, title: string) => {
        const confirmed = confirm(
            `Delete job description "${title}"?\n\n` +
                'This will ALSO delete every resume submitted under this JD ' +
                "(and the underlying files). This can't be undone.",
        );
        if (!confirmed) return;
        const res = await api.deleteJD(id);
        if (form.id === id) startNew();
        await refresh();
        if (res?.deleted_resumes) {
            alert(
                `Deleted JD and ${res.deleted_resumes} resume${
                    res.deleted_resumes === 1 ? '' : 's'
                }.`,
            );
        }
    };

    return (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-6">
            <section className="space-y-3">
                <div className="flex items-center justify-between">
                    <h1 className="text-2xl font-semibold">
                        {form.id == null
                            ? 'New job description'
                            : `Editing #${form.id}`}
                    </h1>
                    {form.id != null && (
                        <button
                            onClick={startNew}
                            className="text-sm text-blue-600 hover:underline"
                        >
                            + New
                        </button>
                    )}
                </div>

                <input
                    className="w-full border rounded px-3 py-2"
                    placeholder="Title (e.g. Senior Backend Engineer)"
                    value={form.title}
                    onChange={(e) =>
                        setForm({ ...form, title: e.target.value })
                    }
                />
                <textarea
                    className="w-full border rounded px-3 py-2 h-72 font-mono text-sm"
                    placeholder="Paste the full JD here (markdown ok)"
                    value={form.body}
                    onChange={(e) => setForm({ ...form, body: e.target.value })}
                />
                <input
                    className="w-full border rounded px-3 py-2"
                    placeholder="Required skills, comma-separated (e.g. Python, Django, PostgreSQL)"
                    value={form.skills}
                    onChange={(e) =>
                        setForm({ ...form, skills: e.target.value })
                    }
                />
                <button
                    onClick={save}
                    disabled={saving || !form.title || !form.body}
                    className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded"
                >
                    {saving
                        ? 'Saving…'
                        : form.id == null
                        ? 'Create JD'
                        : 'Save changes'}
                </button>

                {form.id != null && <CustomFieldsCard jdId={form.id} />}
            </section>

            <aside className="space-y-2">
                <h2 className="text-lg font-semibold">Saved JDs</h2>
                <p className="text-xs text-slate-500">
                    Click a row to edit. Deleting a JD also deletes every
                    resume you uploaded against it.
                </p>
                <div className="border rounded bg-white divide-y">
                    {list.length === 0 && (
                        <div className="p-4 text-sm text-slate-500">
                            No job descriptions yet.
                        </div>
                    )}
                    {list.map((jd) => {
                        const isOpen = form.id === jd.id;
                        return (
                            <div
                                key={jd.id}
                                className={
                                    'p-3 text-sm flex items-start gap-2 ' +
                                    (isOpen ? 'bg-blue-50/60' : 'bg-white')
                                }
                            >
                                <button
                                    onClick={() => loadForEdit(jd.id)}
                                    className="flex-1 text-left"
                                >
                                    <div className="font-medium">
                                        {jd.title || 'Untitled JD'}
                                    </div>
                                    <div className="text-xs text-slate-500 mt-0.5">
                                        Updated {formatDate(jd.updated_at)}
                                    </div>
                                </button>
                                <button
                                    onClick={() => remove(jd.id, jd.title)}
                                    className="text-xs text-red-600 hover:underline shrink-0"
                                >
                                    delete
                                </button>
                            </div>
                        );
                    })}
                </div>
            </aside>
        </div>
    );
}

function CustomFieldsCard({ jdId }: { jdId: number }) {
    const [fields, setFields] = useState<CustomField[]>([]);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [type, setType] = useState<CustomField['type']>('bool');
    const [creating, setCreating] = useState(false);
    const [createError, setCreateError] = useState<string | null>(null);
    const [reextracting, setReextracting] = useState(false);
    const [reextractMsg, setReextractMsg] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editDraft, setEditDraft] = useState<{
        name: string;
        description: string;
        type: CustomField['type'];
    }>({ name: '', description: '', type: 'bool' });
    const [editError, setEditError] = useState<string | null>(null);

    const refresh = async () => {
        const rows = await api.listJDCustomFields(jdId);
        setFields(rows);
    };

    useEffect(() => {
        setReextractMsg(null);
        setEditingId(null);
        refresh().catch(() => setFields([]));
    }, [jdId]);

    const create = async () => {
        if (!name.trim() || !description.trim()) {
            setCreateError('Name and description are both required.');
            return;
        }
        setCreating(true);
        setCreateError(null);
        try {
            await api.createJDCustomField(jdId, {
                name: name.trim(),
                description: description.trim(),
                type,
            });
            setName('');
            setDescription('');
            setType('bool');
            await refresh();
        } catch (e) {
            setCreateError(String(e));
        } finally {
            setCreating(false);
        }
    };

    const remove = async (id: number, label: string) => {
        if (!confirm(`Delete custom field "${label}"? This can't be undone.`))
            return;
        await api.deleteJDCustomField(jdId, id);
        await refresh();
    };

    const startEdit = (f: CustomField) => {
        setEditingId(f.id);
        setEditDraft({
            name: f.name,
            description: f.description,
            type: f.type,
        });
        setEditError(null);
    };

    const cancelEdit = () => {
        setEditingId(null);
        setEditError(null);
    };

    const saveEdit = async (id: number) => {
        const n = editDraft.name.trim();
        const d = editDraft.description.trim();
        if (!n || !d) {
            setEditError('Name and description are required.');
            return;
        }
        try {
            await api.updateJDCustomField(jdId, id, {
                name: n,
                description: d,
                type: editDraft.type,
            });
            cancelEdit();
            await refresh();
        } catch (e) {
            setEditError(String(e));
        }
    };

    const reextract = async () => {
        const ok = confirm(
            `Re-run AI extraction on every resume uploaded against this JD? ` +
                `This will overwrite existing extractions (recruiter edits ` +
                `included) so the new custom fields get applied.`,
        );
        if (!ok) return;
        setReextracting(true);
        setReextractMsg(null);
        try {
            const res = await api.reextractJD(jdId);
            setReextractMsg(
                res.queued === 0
                    ? 'No resumes are scoped to this JD yet.'
                    : `Queued ${res.queued} resume${
                          res.queued === 1 ? '' : 's'
                      } for re-extraction. Watch progress on the Upload page.`,
            );
        } catch (e) {
            setReextractMsg(`Re-extract failed: ${e}`);
        } finally {
            setReextracting(false);
        }
    };

    return (
        <div className="rounded border bg-white p-4 space-y-3">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">
                    Custom fields for this JD
                </h3>
                <button
                    onClick={reextract}
                    disabled={reextracting}
                    className="text-xs text-emerald-700 hover:underline disabled:opacity-50"
                >
                    {reextracting
                        ? 'Re-queueing…'
                        : 'Re-run extraction on all resumes'}
                </button>
            </div>
            <p className="text-xs text-slate-500">
                These fields are injected into the extraction prompt only when
                a resume is being scored against this JD. Edit / add fields
                here, then click <em>Re-run extraction</em> so historical
                resumes pick up the changes.
            </p>

            {fields.length === 0 ? (
                <div className="text-sm text-slate-500 italic">
                    No JD-scoped custom fields yet.
                </div>
            ) : (
                <ul className="divide-y border rounded">
                    {fields.map((f) => {
                        const isEditing = editingId === f.id;
                        return (
                            <li
                                key={f.id}
                                className="p-2 text-sm flex items-start gap-3"
                            >
                                <div className="flex-1 space-y-1">
                                    {isEditing ? (
                                        <>
                                            <div className="grid grid-cols-1 md:grid-cols-[1fr_120px] gap-2">
                                                <input
                                                    className="border rounded px-2 py-1 text-xs font-mono"
                                                    value={editDraft.name}
                                                    onChange={(e) =>
                                                        setEditDraft({
                                                            ...editDraft,
                                                            name: e.target.value,
                                                        })
                                                    }
                                                    autoFocus
                                                />
                                                <select
                                                    className="border rounded px-2 py-1 text-xs"
                                                    value={editDraft.type}
                                                    onChange={(e) =>
                                                        setEditDraft({
                                                            ...editDraft,
                                                            type: e.target
                                                                .value as CustomField['type'],
                                                        })
                                                    }
                                                >
                                                    {FIELD_TYPES.map((t) => (
                                                        <option key={t} value={t}>
                                                            {t}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                            <input
                                                className="border rounded px-2 py-1 text-xs w-full"
                                                value={editDraft.description}
                                                onChange={(e) =>
                                                    setEditDraft({
                                                        ...editDraft,
                                                        description:
                                                            e.target.value,
                                                    })
                                                }
                                            />
                                            {editError && (
                                                <div className="text-xs text-red-600">
                                                    {editError}
                                                </div>
                                            )}
                                        </>
                                    ) : (
                                        <>
                                            <div className="font-mono text-xs">
                                                {f.name}{' '}
                                                <span className="text-slate-400">
                                                    ({f.type})
                                                </span>
                                            </div>
                                            <div className="text-xs text-slate-600">
                                                {f.description}
                                            </div>
                                        </>
                                    )}
                                </div>
                                <div className="space-x-3 whitespace-nowrap">
                                    {isEditing ? (
                                        <>
                                            <button
                                                onClick={() => saveEdit(f.id)}
                                                className="text-xs text-blue-600 hover:underline"
                                            >
                                                save
                                            </button>
                                            <button
                                                onClick={cancelEdit}
                                                className="text-xs text-slate-500 hover:underline"
                                            >
                                                cancel
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                onClick={() => startEdit(f)}
                                                className="text-xs text-blue-600 hover:underline"
                                            >
                                                edit
                                            </button>
                                            <button
                                                onClick={() =>
                                                    remove(f.id, f.name)
                                                }
                                                className="text-xs text-red-600 hover:underline"
                                            >
                                                delete
                                            </button>
                                        </>
                                    )}
                                </div>
                            </li>
                        );
                    })}
                </ul>
            )}

            <div className="border-t pt-3 space-y-2">
                <div className="grid grid-cols-1 md:grid-cols-[1fr_120px] gap-2">
                    <input
                        className="border rounded px-3 py-2 text-sm"
                        placeholder="Field name (snake_case)"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                    />
                    <select
                        className="border rounded px-3 py-2 text-sm"
                        value={type}
                        onChange={(e) =>
                            setType(e.target.value as CustomField['type'])
                        }
                    >
                        {FIELD_TYPES.map((t) => (
                            <option key={t} value={t}>
                                {t}
                            </option>
                        ))}
                    </select>
                </div>
                <input
                    className="border rounded px-3 py-2 text-sm w-full"
                    placeholder="Description for the LLM (e.g. true if the resume lists any current AWS certification)"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                />
                <button
                    onClick={create}
                    disabled={creating}
                    className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm"
                >
                    {creating ? 'Adding…' : '+ Add custom field'}
                </button>
                {createError && (
                    <div className="text-xs text-red-600">{createError}</div>
                )}
            </div>

            {reextractMsg && (
                <div className="text-xs bg-emerald-50 text-emerald-800 rounded p-2">
                    {reextractMsg}
                </div>
            )}
        </div>
    );
}
