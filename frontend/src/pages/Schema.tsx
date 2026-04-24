import { useEffect, useState } from "react";
import { Alias, api, CustomField } from "../api";

export default function SchemaPage() {
  const [tab, setTab] = useState<"fields" | "aliases">("fields");
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Schema</h1>
      <div className="flex gap-2 text-sm border-b">
        {(["fields", "aliases"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 -mb-px border-b-2 ${
              tab === t ? "border-blue-600 text-blue-600" : "border-transparent text-slate-500"
            }`}
          >
            {t === "fields" ? "Custom fields" : "Skill aliases"}
          </button>
        ))}
      </div>
      {tab === "fields" ? <CustomFieldsTab /> : <AliasesTab />}
    </div>
  );
}

function CustomFieldsTab() {
  const [fields, setFields] = useState<CustomField[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<CustomField["type"]>("bool");

  const refresh = () => api.listCustomFields().then(setFields);
  useEffect(() => {
    refresh();
  }, []);

  const add = async () => {
    if (!name || !description) return;
    await api.createCustomField({ name, description, type });
    setName("");
    setDescription("");
    refresh();
  };

  return (
    <div className="space-y-4 max-w-3xl">
      <p className="text-sm text-slate-500">
        Define recruiter-specific fields. They're added to every future extraction and become
        filterable on the dashboard.
      </p>
      <div className="grid grid-cols-[1fr_2fr_auto_auto] gap-2">
        <input
          className="border rounded px-2 py-1"
          placeholder="name (e.g. aws_certified)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="border rounded px-2 py-1"
          placeholder="description (prompts the model)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <select
          className="border rounded px-2 py-1"
          value={type}
          onChange={(e) => setType(e.target.value as CustomField["type"])}
        >
          <option value="bool">bool</option>
          <option value="text">text</option>
          <option value="list">list</option>
          <option value="number">number</option>
        </select>
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
            <th className="text-left px-3 py-2">Name</th>
            <th className="text-left px-3 py-2">Type</th>
            <th className="text-left px-3 py-2">Description</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => (
            <tr key={f.id} className="border-t">
              <td className="px-3 py-2 font-mono">{f.name}</td>
              <td className="px-3 py-2">{f.type}</td>
              <td className="px-3 py-2">{f.description}</td>
              <td className="px-3 py-2">
                <button
                  onClick={() => api.deleteCustomField(f.id).then(refresh)}
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

function AliasesTab() {
  const [rows, setRows] = useState<Alias[]>([]);
  const [alias, setAlias] = useState("");
  const [canonical, setCanonical] = useState("");
  const [kind, setKind] = useState("skill");

  const refresh = () => api.listAliases().then(setRows);
  useEffect(() => {
    refresh();
  }, []);

  const add = async () => {
    if (!alias || !canonical) return;
    await api.upsertAlias({ alias, canonical, kind });
    setAlias("");
    setCanonical("");
    refresh();
  };

  return (
    <div className="space-y-4 max-w-3xl">
      <p className="text-sm text-slate-500">
        Aliases map messy model outputs to canonical names. Corrections from the Verify page
        automatically land here.
      </p>
      <div className="grid grid-cols-[1fr_1fr_auto_auto] gap-2">
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
        <select
          className="border rounded px-2 py-1"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="skill">skill</option>
          <option value="university">university</option>
          <option value="degree">degree</option>
        </select>
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
            <th className="text-left px-3 py-2">Kind</th>
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
              <td className="px-3 py-2">{r.kind}</td>
              <td className="px-3 py-2 text-xs">{r.source}</td>
              <td className="px-3 py-2">{r.frequency}</td>
              <td className="px-3 py-2">
                <button
                  onClick={() => api.deleteAlias(r.kind, r.alias).then(refresh)}
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
