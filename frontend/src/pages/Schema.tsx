import { useEffect, useState } from 'react';
import { Alias, api } from '../api';

export default function SchemaPage() {
    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-semibold">Schema</h1>
            <AliasesPanel />
        </div>
    );
}

function AliasesPanel() {
    const [rows, setRows] = useState<Alias[]>([]);
    const [alias, setAlias] = useState('');
    const [canonical, setCanonical] = useState('');

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

    return (
        <div className="space-y-4 max-w-3xl">
            <p className="text-sm text-slate-500">
                Skill aliases map messy model outputs to canonical names.
                Corrections saved with alias learning from the Verify page
                automatically land here.
            </p>
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
                    {rows.map((r) => (
                        <tr key={`${r.kind}:${r.alias}`} className="border-t">
                            <td className="px-3 py-2 font-mono">{r.alias}</td>
                            <td className="px-3 py-2">{r.canonical}</td>
                            <td className="px-3 py-2 text-xs">{r.source}</td>
                            <td className="px-3 py-2">{r.frequency}</td>
                            <td className="px-3 py-2">
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
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
