import { useContext, useEffect, useState } from 'react';
import {
    UNSAFE_NavigationContext,
    useNavigate,
    useParams,
} from 'react-router-dom';
import {
    api,
    Contact,
    EducationEntry,
    ExperienceEntry,
    Extraction,
    JDSummary,
    ProjectEntry,
    Resume,
} from '../api';

const EMPTY_CONTACT: Contact = {
    name: null,
    email: null,
    phone: null,
    linkedin: null,
    github: null,
    website: null,
};

function normalizeProject(p: unknown): ProjectEntry {
    if (!p || typeof p !== 'object') {
        return { name: null, description_bullets: [], tags: [] };
    }
    const raw = p as Record<string, unknown>;
    const tags = Array.isArray(raw.tags)
        ? (raw.tags as string[])
        : Array.isArray(raw.technologies)
          ? (raw.technologies as string[])
          : [];
    let bullets: string[] = [];
    if (Array.isArray(raw.description_bullets)) {
        bullets = raw.description_bullets as string[];
    } else if (typeof raw.description === 'string' && raw.description.trim()) {
        bullets = [raw.description];
    }
    return {
        name: typeof raw.name === 'string' ? raw.name : null,
        description_bullets: bullets,
        tags,
    };
}

const EMPTY_EDUCATION: EducationEntry = {
    institution: null,
    degree: null,
    major: null,
    gpa: null,
    start_date: null,
    end_date: null,
};

function normalizeEducation(e: unknown): EducationEntry {
    if (!e || typeof e !== 'object') return { ...EMPTY_EDUCATION };
    const raw = e as Record<string, unknown>;
    const legacyEnd =
        typeof raw.graduation_date === 'string'
            ? (raw.graduation_date as string)
            : null;
    return {
        institution:
            typeof raw.institution === 'string'
                ? raw.institution
                : typeof raw.university === 'string'
                  ? (raw.university as string)
                  : null,
        degree: typeof raw.degree === 'string' ? raw.degree : null,
        major: typeof raw.major === 'string' ? raw.major : null,
        gpa: typeof raw.gpa === 'string' ? raw.gpa : null,
        start_date:
            typeof raw.start_date === 'string'
                ? (raw.start_date as string)
                : null,
        end_date:
            typeof raw.end_date === 'string'
                ? (raw.end_date as string)
                : legacyEnd,
    };
}

const EMPTY_EXPERIENCE: ExperienceEntry = {
    company: null,
    role: null,
    start_date: null,
    end_date: null,
    description_bullets: [],
};

function normalizeExperience(x: unknown): ExperienceEntry {
    if (!x || typeof x !== 'object') return { ...EMPTY_EXPERIENCE };
    const raw = x as Record<string, unknown>;
    let start: string | null =
        typeof raw.start_date === 'string' ? (raw.start_date as string) : null;
    let end: string | null =
        typeof raw.end_date === 'string' ? (raw.end_date as string) : null;
    if (!start && !end && typeof raw.dates === 'string') {
        const [s, e] = splitLegacyDates(raw.dates as string);
        start = s;
        end = e;
    }
    return {
        company: typeof raw.company === 'string' ? raw.company : null,
        role: typeof raw.role === 'string' ? raw.role : null,
        start_date: start,
        end_date: end,
        description_bullets: Array.isArray(raw.description_bullets)
            ? (raw.description_bullets as string[])
            : [],
    };
}

function splitLegacyDates(text: string): [string | null, string | null] {
    const t = text.trim();
    if (!t) return [null, null];
    for (const sep of [' - ', ' – ', '—', ' to ', '-', '–']) {
        const idx = t.indexOf(sep);
        if (idx >= 0) {
            return [
                t.slice(0, idx).trim() || null,
                t.slice(idx + sep.length).trim() || null,
            ];
        }
    }
    return [null, t];
}

function normalizeExtraction(
    extraction: Partial<Extraction> | null | undefined,
    resume: Resume,
): Extraction {
    const e = extraction ?? {};
    return {
        is_resume: e.is_resume ?? resume.is_resume,
        validity_confidence:
            e.validity_confidence ?? resume.validity_confidence,
        validity_reason: e.validity_reason ?? resume.validity_reason ?? '',
        contact: { ...EMPTY_CONTACT, ...(e.contact ?? {}) },
        education: Array.isArray(e.education)
            ? e.education.map(normalizeEducation)
            : [],
        experience: Array.isArray(e.experience)
            ? e.experience.map(normalizeExperience)
            : [],
        projects: Array.isArray(e.projects)
            ? e.projects.map(normalizeProject)
            : [],
        technical_skills: Array.isArray(e.technical_skills)
            ? e.technical_skills
            : [],
        awards: Array.isArray(e.awards) ? e.awards : [],
        certificates: Array.isArray(e.certificates) ? e.certificates : [],
        calculated_yoe: e.calculated_yoe ?? null,
        concerns: Array.isArray(e.concerns) ? e.concerns : [],
        custom: e.custom ?? {},
    };
}

type NavigationTx = { retry: () => void };
type BlockNavigator = {
    block?: (blocker: (tx: NavigationTx) => void) => () => void;
};

function useBrowserNavigationBlock(when: boolean, message: string) {
    const { navigator } = useContext(UNSAFE_NavigationContext);

    useEffect(() => {
        if (!when) return;
        const nav = navigator as BlockNavigator;
        if (typeof nav.block !== 'function') return;

        const unblock = nav.block((tx) => {
            const confirmed = window.confirm(message);
            if (!confirmed) return;
            unblock();
            tx.retry();
        });
        return unblock;
    }, [navigator, when, message]);
}

export default function Verify() {
    const { id } = useParams();
    const nav = useNavigate();
    const [resume, setResume] = useState<Resume | null>(null);
    const [draft, setDraft] = useState<Extraction | null>(null);
    const [customText, setCustomText] = useState('{}');
    const [customError, setCustomError] = useState<string | null>(null);
    const [applyAliasLearning, setApplyAliasLearning] = useState(false);
    const [saving, setSaving] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [jds, setJds] = useState<JDSummary[]>([]);
    const [scoreJdId, setScoreJdId] = useState<number | ''>('');
    const [scoring, setScoring] = useState(false);
    const [scoreError, setScoreError] = useState<string | null>(null);
    const [initialDraftJson, setInitialDraftJson] = useState('');
    const [initialCustomText, setInitialCustomText] = useState('{}');
    const [allowNavigation, setAllowNavigation] = useState(false);

    useEffect(() => {
        if (!id) return;
        api.getResume(Number(id)).then((r) => {
            const next = normalizeExtraction(r.extraction, r);
            const nextCustomText = JSON.stringify(next.custom ?? {}, null, 2);
            setResume(r);
            setDraft(next);
            setCustomText(nextCustomText);
            setScoreJdId(r.scored_against_jd_id ?? '');
            setInitialDraftJson(JSON.stringify(next));
            setInitialCustomText(nextCustomText);
            setAllowNavigation(false);
        });
        api.listJDs()
            .then(setJds)
            .catch(() => setJds([]));
    }, [id]);

    const draftJson = draft ? JSON.stringify(draft) : '';
    const hasUnsavedChanges =
        Boolean(resume && draft) &&
        (draftJson !== initialDraftJson || customText !== initialCustomText);
    const shouldWarnBeforeLeave =
        hasUnsavedChanges && !saving && !deleting && !allowNavigation;
    useBrowserNavigationBlock(
        shouldWarnBeforeLeave,
        'You have unsaved changes. Leave this page without saving?',
    );

    useEffect(() => {
        if (!shouldWarnBeforeLeave) return;
        const onBeforeUnload = (e: BeforeUnloadEvent) => {
            e.preventDefault();
            e.returnValue = '';
        };
        window.addEventListener('beforeunload', onBeforeUnload);
        return () => window.removeEventListener('beforeunload', onBeforeUnload);
    }, [shouldWarnBeforeLeave]);

    if (!resume || !draft) return <div>Loading…</div>;

    const update = (patch: Partial<Extraction>) =>
        setDraft({ ...draft, ...patch });
    const updateContact = (patch: Partial<Contact>) =>
        update({ contact: { ...draft.contact, ...patch } });

    const save = async () => {
        let parsedCustom: Record<string, unknown> = {};
        try {
            const parsed = JSON.parse(customText || '{}');
            if (
                parsed &&
                typeof parsed === 'object' &&
                !Array.isArray(parsed)
            ) {
                parsedCustom = parsed as Record<string, unknown>;
            } else {
                setCustomError(
                    'Custom fields must be a JSON object, for example {"aws_certified": true}.',
                );
                return;
            }
            setCustomError(null);
        } catch {
            setCustomError('Custom fields JSON is invalid.');
            return;
        }

        setSaving(true);
        try {
            const payload: Extraction = { ...draft, custom: parsedCustom };
            const updated = await api.verifyResume(
                resume.id,
                payload,
                applyAliasLearning,
            );
            setResume(updated);
            setAllowNavigation(true);
            nav('/upload');
        } finally {
            setSaving(false);
        }
    };

    const scoreNow = async () => {
        if (scoreJdId === '') return;
        setScoring(true);
        setScoreError(null);
        try {
            const updated = await api.scoreResume(resume.id, scoreJdId);
            setResume(updated);
        } catch (e) {
            setScoreError(String(e));
        } finally {
            setScoring(false);
        }
    };

    const remove = async () => {
        if (!confirm(`Delete ${resume.filename}? This can't be undone.`))
            return;
        setDeleting(true);
        try {
            await api.deleteResume(resume.id);
            setAllowNavigation(true);
            nav('/upload');
        } finally {
            setDeleting(false);
        }
    };

    const skillsText = (draft.technical_skills ?? []).join(', ');
    const fileUrl = api.resumeFileUrl(resume.id);
    const isPdf = resume.mime_type.includes('pdf');
    const isImage = resume.mime_type.startsWith('image/');

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <section>
                <h2 className="font-medium mb-2">Source document</h2>
                <div className="border rounded bg-white p-4 text-sm space-y-4">
                    <div className="flex items-start justify-between gap-4">
                        <div>
                            <div className="font-mono">{resume.filename}</div>
                            <div className="text-slate-500 mt-1">
                                {resume.mime_type}
                            </div>
                        </div>
                        <button
                            onClick={remove}
                            disabled={deleting}
                            className="text-xs text-red-600 hover:underline disabled:opacity-50"
                        >
                            {deleting ? 'Deleting…' : 'Delete resume'}
                        </button>
                    </div>

                    <a
                        href={fileUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline text-sm"
                    >
                        Open original file in a new tab
                    </a>

                    <div className="border rounded overflow-hidden bg-slate-50">
                        {isPdf && (
                            <iframe
                                title="Resume preview"
                                src={fileUrl}
                                className="w-full h-[680px]"
                            />
                        )}
                        {isImage && (
                            <img
                                src={fileUrl}
                                alt="Resume preview"
                                className="w-full h-auto max-h-[680px] object-contain bg-white"
                            />
                        )}
                        {!isPdf && !isImage && (
                            <div className="p-4 text-sm text-slate-600">
                                Preview is currently supported for PDF and image
                                uploads. Use the link above to open this
                                document.
                            </div>
                        )}
                    </div>

                    <details className="text-xs">
                        <summary className="cursor-pointer text-slate-600">
                            Raw LLM extraction JSON
                        </summary>
                        <pre className="mt-2 overflow-auto bg-slate-900 text-slate-100 rounded p-3 text-[11px] leading-relaxed">
                            {JSON.stringify(resume.extraction_raw, null, 2)}
                        </pre>
                    </details>
                </div>
            </section>

            <section className="space-y-3">
                <h2 className="font-medium">Extraction (edit to correct)</h2>

                {resume.validity_reason && (
                    <div className="rounded border bg-slate-50 text-slate-700 text-xs p-3">
                        <span className="font-medium">Validity reason:</span>{' '}
                        {resume.validity_reason}
                    </div>
                )}

                <Group
                    title={
                        resume.scored_against_jd_id
                            ? 'Score against a different JD'
                            : 'Score this resume against a JD'
                    }
                >
                    <p className="text-xs text-slate-500 -mt-1 mb-1">
                        {resume.scored_against_jd_id
                            ? `Currently scored against ${
                                  jds.find(
                                      (j) =>
                                          j.id === resume.scored_against_jd_id,
                                  )?.title ??
                                  `JD #${resume.scored_against_jd_id}`
                              }. Pick another JD to re-score.`
                            : 'This resume was parsed without a JD. Pick one to score it now.'}
                    </p>
                    <div className="flex gap-2 items-center">
                        <select
                            className="input flex-1"
                            value={scoreJdId}
                            onChange={(e) =>
                                setScoreJdId(
                                    e.target.value === ''
                                        ? ''
                                        : Number(e.target.value),
                                )
                            }
                        >
                            <option value="">Select a JD…</option>
                            {jds.map((jd) => (
                                <option key={jd.id} value={jd.id}>
                                    {jd.title}
                                </option>
                            ))}
                        </select>
                        <button
                            onClick={scoreNow}
                            disabled={
                                scoring ||
                                scoreJdId === '' ||
                                resume.is_rejected
                            }
                            className="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-2 rounded text-sm disabled:opacity-50"
                        >
                            {scoring ? 'Scoring…' : 'Score now'}
                        </button>
                    </div>
                    {scoreError && (
                        <div className="text-xs text-red-600 mt-1">
                            {scoreError}
                        </div>
                    )}
                    {resume.score != null && (
                        <div className="text-xs text-slate-600 mt-1">
                            Current score:{' '}
                            <span className="font-medium">
                                {Math.round(resume.score)}
                            </span>
                            {resume.match_tier && ` · ${resume.match_tier}`}
                        </div>
                    )}
                </Group>

                <Group title="Contact">
                    <Field label="Name">
                        <input
                            className="input"
                            value={draft.contact.name ?? ''}
                            onChange={(e) =>
                                updateContact({ name: e.target.value || null })
                            }
                        />
                    </Field>
                    <Field label="Email">
                        <input
                            className="input"
                            value={draft.contact.email ?? ''}
                            onChange={(e) =>
                                updateContact({ email: e.target.value || null })
                            }
                        />
                    </Field>
                    <Field label="Phone">
                        <input
                            className="input"
                            value={draft.contact.phone ?? ''}
                            onChange={(e) =>
                                updateContact({ phone: e.target.value || null })
                            }
                        />
                    </Field>
                    <Field label="LinkedIn">
                        <input
                            className="input"
                            value={draft.contact.linkedin ?? ''}
                            onChange={(e) =>
                                updateContact({
                                    linkedin: e.target.value || null,
                                })
                            }
                        />
                    </Field>
                    <Field label="GitHub">
                        <input
                            className="input"
                            value={draft.contact.github ?? ''}
                            onChange={(e) =>
                                updateContact({
                                    github: e.target.value || null,
                                })
                            }
                        />
                    </Field>
                    <Field label="Website / Portfolio">
                        <input
                            className="input"
                            placeholder="e.g. johndoe.dev, kaggle.com/..."
                            value={draft.contact.website ?? ''}
                            onChange={(e) =>
                                updateContact({
                                    website: e.target.value || null,
                                })
                            }
                        />
                    </Field>
                </Group>

                <Group title="Calculated years of experience">
                    <input
                        className="input"
                        type="number"
                        step="0.5"
                        value={draft.calculated_yoe ?? ''}
                        onChange={(e) =>
                            update({
                                calculated_yoe:
                                    e.target.value === ''
                                        ? null
                                        : Number(e.target.value),
                            })
                        }
                    />
                </Group>

                <Group title="Concerns / questions to ask the candidate">
                    <p className="text-xs text-slate-500 -mt-1 mb-1">
                        Neutral observations the recruiter may want to ask about
                        (e.g. timeline gaps, very short tenures). Does not
                        affect scoring.
                    </p>
                    <BulletsEditor
                        bullets={draft.concerns ?? []}
                        onChange={(concerns) => update({ concerns })}
                        placeholder="e.g. Gap of ~10 months between roles in 2024."
                    />
                </Group>

                <Group title="Education">
                    <EducationEditor
                        items={draft.education}
                        onChange={(education) => update({ education })}
                    />
                </Group>

                <Group title="Experience">
                    <ExperienceEditor
                        items={draft.experience}
                        onChange={(experience) => update({ experience })}
                    />
                </Group>

                <Group title="Projects">
                    <ProjectEditor
                        items={draft.projects}
                        onChange={(projects) => update({ projects })}
                    />
                </Group>

                <Group title="Technical skills (comma-separated)">
                    <input
                        className="input"
                        value={skillsText}
                        onChange={(e) =>
                            update({
                                technical_skills: e.target.value
                                    .split(',')
                                    .map((s) => s.trim())
                                    .filter(Boolean),
                            })
                        }
                    />
                </Group>

                <Group title="Awards">
                    <BulletsEditor
                        bullets={draft.awards ?? []}
                        onChange={(awards) => update({ awards })}
                        placeholder="e.g. MATE ROV World Championship – 13th place"
                    />
                </Group>

                <Group title="Certificates">
                    <BulletsEditor
                        bullets={draft.certificates ?? []}
                        onChange={(certificates) => update({ certificates })}
                        placeholder="e.g. AWS Certified Solutions Architect"
                    />
                </Group>

                <Group title="Custom fields JSON">
                    <textarea
                        className="input min-h-[140px] font-mono text-xs"
                        value={customText}
                        onChange={(e) => {
                            setCustomText(e.target.value);
                            setCustomError(null);
                        }}
                    />
                    {customError && (
                        <div className="text-xs text-red-600 mt-1">
                            {customError}
                        </div>
                    )}
                </Group>

                <div className="rounded border bg-slate-50 p-3 text-sm">
                    <label className="inline-flex items-start gap-2">
                        <input
                            type="checkbox"
                            checked={applyAliasLearning}
                            onChange={(e) =>
                                setApplyAliasLearning(e.target.checked)
                            }
                            className="mt-0.5"
                        />
                        <span>
                            Apply skill corrections to alias learning for future
                            resumes.
                            <div className="text-xs text-slate-500 mt-1">
                                Keep this unchecked if changes are one-off.
                            </div>
                        </span>
                    </label>
                </div>

                <div className="pt-4">
                    <button
                        onClick={save}
                        disabled={saving}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded disabled:opacity-50"
                    >
                        {saving ? 'Saving…' : 'Save corrections'}
                    </button>
                </div>

                <style>{`.input { display:block; width:100%; border:1px solid #e2e8f0; border-radius:6px; padding: 6px 10px; font-size: 14px; background: white; } .input + .input { margin-top: 6px; }`}</style>
            </section>
        </div>
    );
}

function Group({
    title,
    children,
}: {
    title: string;
    children: React.ReactNode;
}) {
    return (
        <div className="rounded border bg-white p-3 space-y-2">
            <div className="text-xs uppercase tracking-wide text-slate-500">
                {title}
            </div>
            {children}
        </div>
    );
}

function Field({
    label,
    children,
}: {
    label: string;
    children: React.ReactNode;
}) {
    return (
        <label className="block text-sm">
            <span className="block text-slate-500 text-xs mb-1">{label}</span>
            {children}
        </label>
    );
}

function RowField({
    label,
    children,
}: {
    label: string;
    children: React.ReactNode;
}) {
    return (
        <div className="grid grid-cols-[120px_1fr] gap-3 items-center">
            <span className="text-xs uppercase tracking-wide text-slate-500">
                {label}
            </span>
            {children}
        </div>
    );
}

function EducationEditor({
    items,
    onChange,
}: {
    items: EducationEntry[];
    onChange: (next: EducationEntry[]) => void;
}) {
    const update = (i: number, patch: Partial<EducationEntry>) => {
        const next = [...items];
        next[i] = { ...next[i], ...patch };
        onChange(next);
    };
    const remove = (i: number) => {
        const next = [...items];
        next.splice(i, 1);
        onChange(next);
    };
    return (
        <div className="space-y-3">
            {items.map((edu, i) => (
                <div
                    key={i}
                    className="border rounded p-3 space-y-2 bg-slate-50"
                >
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-500">
                            Entry #{i + 1}
                        </span>
                        <button
                            className="text-xs text-red-600 hover:underline"
                            onClick={() => remove(i)}
                        >
                            remove
                        </button>
                    </div>
                    <RowField label="Institution">
                        <input
                            className="input"
                            value={edu.institution ?? ''}
                            onChange={(e) =>
                                update(i, {
                                    institution: e.target.value || null,
                                })
                            }
                        />
                    </RowField>
                    <RowField label="Degree">
                        <input
                            className="input"
                            placeholder="e.g. Bachelor of Science"
                            value={edu.degree ?? ''}
                            onChange={(e) =>
                                update(i, { degree: e.target.value || null })
                            }
                        />
                    </RowField>
                    <RowField label="Major">
                        <input
                            className="input"
                            placeholder="e.g. Computer Science"
                            value={edu.major ?? ''}
                            onChange={(e) =>
                                update(i, { major: e.target.value || null })
                            }
                        />
                    </RowField>
                    <RowField label="GPA">
                        <input
                            className="input"
                            placeholder="optional"
                            value={edu.gpa ?? ''}
                            onChange={(e) =>
                                update(i, { gpa: e.target.value || null })
                            }
                        />
                    </RowField>
                    <RowField label="Start date">
                        <input
                            className="input"
                            placeholder="optional, e.g. September 2022"
                            value={edu.start_date ?? ''}
                            onChange={(e) =>
                                update(i, {
                                    start_date: e.target.value || null,
                                })
                            }
                        />
                    </RowField>
                    <RowField label="End date">
                        <input
                            className="input"
                            placeholder="e.g. June 2026"
                            value={edu.end_date ?? ''}
                            onChange={(e) =>
                                update(i, {
                                    end_date: e.target.value || null,
                                })
                            }
                        />
                    </RowField>
                </div>
            ))}
            <button
                className="text-sm text-blue-600 hover:underline"
                onClick={() => onChange([...items, { ...EMPTY_EDUCATION }])}
            >
                + Add education
            </button>
        </div>
    );
}

function BulletsEditor({
    bullets,
    onChange,
    placeholder,
}: {
    bullets: string[];
    onChange: (next: string[]) => void;
    placeholder?: string;
}) {
    const update = (i: number, value: string) => {
        const next = [...bullets];
        next[i] = value;
        onChange(next);
    };
    const remove = (i: number) => {
        const next = [...bullets];
        next.splice(i, 1);
        onChange(next);
    };
    return (
        <div className="space-y-2">
            {bullets.map((b, i) => (
                <div key={i} className="flex items-start gap-2">
                    <span className="text-slate-400 select-none pt-2">•</span>
                    <textarea
                        className="input flex-1 min-h-[80px] leading-snug"
                        rows={Math.max(3, b.split('\n').length + 1)}
                        value={b}
                        placeholder={placeholder}
                        onChange={(e) => update(i, e.target.value)}
                    />
                    <button
                        className="text-xs text-red-600 hover:underline pt-2"
                        onClick={() => remove(i)}
                    >
                        ×
                    </button>
                </div>
            ))}
            <button
                className="text-xs text-blue-600 hover:underline"
                onClick={() => onChange([...bullets, ''])}
            >
                + Add bullet
            </button>
        </div>
    );
}

function ExperienceEditor({
    items,
    onChange,
}: {
    items: ExperienceEntry[];
    onChange: (next: ExperienceEntry[]) => void;
}) {
    const update = (i: number, patch: Partial<ExperienceEntry>) => {
        const next = [...items];
        next[i] = { ...next[i], ...patch };
        onChange(next);
    };
    const remove = (i: number) => {
        const next = [...items];
        next.splice(i, 1);
        onChange(next);
    };
    return (
        <div className="space-y-4">
            {items.map((exp, i) => (
                <div
                    key={i}
                    className="border rounded p-3 space-y-2 bg-slate-50"
                >
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-500">
                            Entry #{i + 1}
                        </span>
                        <button
                            className="text-xs text-red-600 hover:underline"
                            onClick={() => remove(i)}
                        >
                            remove
                        </button>
                    </div>
                    <RowField label="Company">
                        <input
                            className="input"
                            value={exp.company ?? ''}
                            onChange={(e) =>
                                update(i, { company: e.target.value || null })
                            }
                        />
                    </RowField>
                    <RowField label="Role">
                        <input
                            className="input"
                            value={exp.role ?? ''}
                            onChange={(e) =>
                                update(i, { role: e.target.value || null })
                            }
                        />
                    </RowField>
                    <RowField label="Start date">
                        <input
                            className="input"
                            placeholder="e.g. January 2026"
                            value={exp.start_date ?? ''}
                            onChange={(e) =>
                                update(i, {
                                    start_date: e.target.value || null,
                                })
                            }
                        />
                    </RowField>
                    <RowField label="End date">
                        <input
                            className="input"
                            placeholder='e.g. "Present" or "December 2025"'
                            value={exp.end_date ?? ''}
                            onChange={(e) =>
                                update(i, {
                                    end_date: e.target.value || null,
                                })
                            }
                        />
                    </RowField>
                    <RowField label="Bullets">
                        <BulletsEditor
                            bullets={exp.description_bullets ?? []}
                            onChange={(next) =>
                                update(i, { description_bullets: next })
                            }
                            placeholder="Describe an accomplishment"
                        />
                    </RowField>
                </div>
            ))}
            <button
                className="text-sm text-blue-600 hover:underline"
                onClick={() => onChange([...items, { ...EMPTY_EXPERIENCE }])}
            >
                + Add experience
            </button>
        </div>
    );
}

function ProjectEditor({
    items,
    onChange,
}: {
    items: ProjectEntry[];
    onChange: (next: ProjectEntry[]) => void;
}) {
    const update = (i: number, patch: Partial<ProjectEntry>) => {
        const next = [...items];
        next[i] = { ...next[i], ...patch };
        onChange(next);
    };
    const remove = (i: number) => {
        const next = [...items];
        next.splice(i, 1);
        onChange(next);
    };
    return (
        <div className="space-y-3">
            {items.map((proj, i) => (
                <div
                    key={i}
                    className="border rounded p-3 space-y-2 bg-slate-50"
                >
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-500">
                            Entry #{i + 1}
                        </span>
                        <button
                            className="text-xs text-red-600 hover:underline"
                            onClick={() => remove(i)}
                        >
                            remove
                        </button>
                    </div>
                    <RowField label="Name">
                        <input
                            className="input"
                            value={proj.name ?? ''}
                            onChange={(e) =>
                                update(i, { name: e.target.value || null })
                            }
                        />
                    </RowField>
                    <RowField label="Tags">
                        <input
                            className="input"
                            placeholder="optional, comma-separated"
                            value={(proj.tags ?? []).join(', ')}
                            onChange={(e) =>
                                update(i, {
                                    tags: e.target.value
                                        .split(',')
                                        .map((s) => s.trim())
                                        .filter(Boolean),
                                })
                            }
                        />
                    </RowField>
                    <RowField label="Bullets">
                        <BulletsEditor
                            bullets={proj.description_bullets ?? []}
                            onChange={(next) =>
                                update(i, { description_bullets: next })
                            }
                            placeholder="Describe what this project does"
                        />
                    </RowField>
                </div>
            ))}
            <button
                className="text-sm text-blue-600 hover:underline"
                onClick={() =>
                    onChange([
                        ...items,
                        { name: '', description_bullets: [], tags: [] },
                    ])
                }
            >
                + Add project
            </button>
        </div>
    );
}
