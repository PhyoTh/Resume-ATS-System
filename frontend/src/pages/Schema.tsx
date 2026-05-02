import { useEffect, useState } from 'react';
import { Alias, CustomField, api } from '../api';

type CustomFieldType = CustomField['type'];

const CUSTOM_FIELD_TYPES: CustomFieldType[] = ['text', 'bool', 'list', 'number'];

export default function SchemaPage() {
    return (
        <div className="space-y-8">
            <h1 className="text-2xl font-semibold">Schema</h1>
            <AliasesPanel />
            <CustomFieldsPanel />
        </div>
    );
}

function AliasesPanel() {
    const [rows, setRows] = useState<Alias[]>([]);
    const [alias, setAlias] = useState('');
    const [canonical, setCanonical] = useState('');
    const [editingKey, setEditingKey] = useState<string | null>(null);
    const [draftCanonical, setDraftCanonical] = useState('');

    const refresh = () => api.listAliases('skill').then(setRows);
    useEffect(() => {
        refresh();
    }, []);

    const add = async () => {
        if (!alias || !canonical) return;
        await api.upsertAlias({ alias, canonical, kind: 'skill' });
        setAlias('');
        setCanonical('');
        refresh();
    };

    const startEdit = (row: Alias) => {
        setEditingKey(`${row.kind}:${row.alias}`);
        setDraftCanonical(row.canonical);
    };

    const cancelEdit = () => {
        setEditingKey(null);
        setDraftCanonical('');
    };

    const saveEdit = async (row: Alias) => {
        const next = draftCanonical.trim();
        if (!next || next === row.canonical) {
            cancelEdit();
            return;
        }
        await api.upsertAlias({
            alias: row.alias,
            canonical: next,
            kind: row.kind,
        });
        cancelEdit();
        refresh();
    };

    return (
        <section className="space-y-4 max-w-3xl">
            <div>
                <h2 className="text-lg font-semibold">Skill aliases</h2>
                <p className="text-sm text-slate-500">
                    Skill aliases map messy model outputs to canonical names.
                    Corrections saved with alias learning from the Verify page
                    automatically land here. Click <em>edit</em> to rename a
                    canonical without deleting and re-adding.
                </p>
            </div>
            <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
                <input
                    className="border rounded px-2 py-1"
                    placeholder="alias"
                    value={alias}
                    onChange={(e) => setAlias(e.target.value)}
                />
                <input
                    className="border rounded px-2 py-1"
                    placeholder="canonical"
                    value={canonical}
                    onChange={(e) => setCanonical(e.target.value)}
                />
                <button
                    onClick={add}
                    className="bg-blue-600 text-white rounded px-3 text-sm hover:bg-blue-700"
                >
                    Add
                </button>
            </div>

            <table className="w-full border rounded bg-white overflow-hidden text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                        <th className="text-left px-3 py-2">Alias</th>
                        <th className="text-left px-3 py-2">→ Canonical</th>
                        <th className="text-left px-3 py-2">Source</th>
                        <th className="text-left px-3 py-2">Freq</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r) => {
                        const key = `${r.kind}:${r.alias}`;
                        const isEditing = editingKey === key;
                        return (
                            <tr key={key} className="border-t">
                                <td className="px-3 py-2 font-mono">{r.alias}</td>
                                <td className="px-3 py-2">
                                    {isEditing ? (
                                        <input
                                            className="border rounded px-2 py-1 w-full"
                                            value={draftCanonical}
                                            onChange={(e) =>
                                                setDraftCanonical(e.target.value)
                                            }
                                            autoFocus
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') saveEdit(r);
                                                if (e.key === 'Escape') cancelEdit();
                                            }}
                                        />
                                    ) : (
                                        r.canonical
                                    )}
                                </td>
                                <td className="px-3 py-2 text-xs">{r.source}</td>
                                <td className="px-3 py-2">{r.frequency}</td>
                                <td className="px-3 py-2 space-x-3 whitespace-nowrap">
                                    {isEditing ? (
                                        <>
                                            <button
                                                onClick={() => saveEdit(r)}
                                                className="text-blue-600 hover:underline"
                                            >
                                                save
                                            </button>
                                            <button
                                                onClick={cancelEdit}
                                                className="text-slate-500 hover:underline"
                                            >
                                                cancel
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                onClick={() => startEdit(r)}
                                                className="text-blue-600 hover:underline"
                                            >
                                                edit
                                            </button>
                                            <button
                                                onClick={() =>
                                                    api
                                                        .deleteAlias(r.kind, r.alias)
                                                        .then(refresh)
                                                }
                                                className="text-red-600 hover:underline"
                                            >
                                                delete
                                            </button>
                                        </>
                                    )}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </section>
    );
}

function CustomFieldsPanel() {
    const [rows, setRows] = useState<CustomField[]>([]);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [type, setType] = useState<CustomFieldType>('text');
    const [editingId, setEditingId] = useState<number | null>(null);
    const [draft, setDraft] = useState<{
        name: string;
        description: string;
        type: CustomFieldType;
    }>({ name: '', description: '', type: 'text' });
    const [error, setError] = useState<string | null>(null);

    const refresh = async () => {
        const all = await api.listCustomFields();
        // Schema page only manages GLOBAL fields. JD-scoped fields are
        // edited from the Job Description page.
        setRows(all.filter((f) => f.job_description_id == null));
    };
    useEffect(() => {
        refresh();
    }, []);

    const add = async () => {
        setError(null);
        const n = name.trim();
        const d = description.trim();
        if (!n || !d) {
            setError('Name and description are required.');
            return;
        }
        try {
            await api.createCustomField({ name: n, description: d, type });
            setName('');
            setDescription('');
            setType('text');
            refresh();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const startEdit = (row: CustomField) => {
        setEditingId(row.id);
        setDraft({
            name: row.name,
            description: row.description,
            type: row.type,
        });
        setError(null);
    };

    const cancelEdit = () => {
        setEditingId(null);
        setError(null);
    };

    const saveEdit = async (id: number) => {
        const n = draft.name.trim();
        const d = draft.description.trim();
        if (!n || !d) {
            setError('Name and description are required.');
            return;
        }
        try {
            await api.updateCustomField(id, {
                name: n,
                description: d,
                type: draft.type,
            });
            cancelEdit();
            refresh();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const remove = async (id: number) => {
        await api.deleteCustomField(id);
        refresh();
    };

    return (
        <section className="space-y-4 max-w-3xl">
            <div>
                <h2 className="text-lg font-semibold">
                    Custom fields (global)
                </h2>
                <p className="text-sm text-slate-500">
                    Recruiter-defined fields injected into every extraction
                    prompt. Extracted values land under the resume's{' '}
                    <code>custom</code> object. JD-specific fields are managed
                    on the Job Description page.
                </p>
            </div>

            <div className="grid grid-cols-[1fr_2fr_auto_auto] gap-2 items-start">
                <input
                    className="border rounded px-2 py-1"
                    placeholder="name (e.g. is_senior)"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                />
                <input
                    className="border rounded px-2 py-1"
                    placeholder="description (what to extract)"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                />
                <select
                    className="border rounded px-2 py-1 bg-white"
                    value={type}
                    onChange={(e) =>
                        setType(e.target.value as CustomFieldType)
                    }
                >
                    {CUSTOM_FIELD_TYPES.map((t) => (
                        <option key={t} value={t}>
                            {t}
                        </option>
                    ))}
                </select>
                <button
                    onClick={add}
                    className="bg-blue-600 text-white rounded px-3 text-sm hover:bg-blue-700"
                >
                    Add
                </button>
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}

            <table className="w-full border rounded bg-white overflow-hidden text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                        <th className="text-left px-3 py-2">Name</th>
                        <th className="text-left px-3 py-2">Description</th>
                        <th className="text-left px-3 py-2">Type</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {rows.length === 0 && (
                        <tr>
                            <td
                                colSpan={4}
                                className="px-3 py-3 text-slate-500 text-center"
                            >
                                No global custom fields yet.
                            </td>
                        </tr>
                    )}
                    {rows.map((r) => {
                        const isEditing = editingId === r.id;
                        return (
                            <tr key={r.id} className="border-t align-top">
                                <td className="px-3 py-2 font-mono">
                                    {isEditing ? (
                                        <input
                                            className="border rounded px-2 py-1 w-full"
                                            value={draft.name}
                                            onChange={(e) =>
                                                setDraft({
                                                    ...draft,
                                                    name: e.target.value,
                                                })
                                            }
                                            autoFocus
                                        />
                                    ) : (
                                        r.name
                                    )}
                                </td>
                                <td className="px-3 py-2">
                                    {isEditing ? (
                                        <input
                                            className="border rounded px-2 py-1 w-full"
                                            value={draft.description}
                                            onChange={(e) =>
                                                setDraft({
                                                    ...draft,
                                                    description: e.target.value,
                                                })
                                            }
                                        />
                                    ) : (
                                        r.description
                                    )}
                                </td>
                                <td className="px-3 py-2">
                                    {isEditing ? (
                                        <select
                                            className="border rounded px-2 py-1 bg-white"
                                            value={draft.type}
                                            onChange={(e) =>
                                                setDraft({
                                                    ...draft,
                                                    type: e.target
                                                        .value as CustomFieldType,
                                                })
                                            }
                                        >
                                            {CUSTOM_FIELD_TYPES.map((t) => (
                                                <option key={t} value={t}>
                                                    {t}
                                                </option>
                                            ))}
                                        </select>
                                    ) : (
                                        <span className="font-mono text-xs">
                                            {r.type}
                                        </span>
                                    )}
                                </td>
                                <td className="px-3 py-2 space-x-3 whitespace-nowrap">
                                    {isEditing ? (
                                        <>
                                            <button
                                                onClick={() => saveEdit(r.id)}
                                                className="text-blue-600 hover:underline"
                                            >
                                                save
                                            </button>
                                            <button
                                                onClick={cancelEdit}
                                                className="text-slate-500 hover:underline"
                                            >
                                                cancel
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                onClick={() => startEdit(r)}
                                                className="text-blue-600 hover:underline"
                                            >
                                                edit
                                            </button>
                                            <button
                                                onClick={() => remove(r.id)}
                                                className="text-red-600 hover:underline"
                                            >
                                                delete
                                            </button>
                                        </>
                                    )}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </section>
    );
}
