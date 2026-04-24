import { useEffect, useState } from 'react';
import { api, JD, JDSummary } from '../api';

const BLANK_FORM = { id: null as number | null, title: '', body: '', skills: '' };

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
            </section>

            <aside className="space-y-2">
                <h2 className="text-lg font-semibold">Saved JDs</h2>
                <p className="text-xs text-slate-500">
                    Click a row to edit. Deleting a JD also deletes every
                    resume that was submitted under it.
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
