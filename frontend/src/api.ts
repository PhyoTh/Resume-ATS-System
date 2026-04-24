export interface Contact {
    name: string | null;
    email: string | null;
    phone: string | null;
    linkedin: string | null;
    github: string | null;
    website: string | null;
}

export interface EducationEntry {
    institution: string | null;
    degree: string | null;
    major: string | null;
    gpa: string | null;
    start_date: string | null;
    end_date: string | null;
}

export interface ExperienceEntry {
    company: string | null;
    role: string | null;
    start_date: string | null;
    end_date: string | null;
    description_bullets: string[];
}

export interface ProjectEntry {
    name: string | null;
    description_bullets: string[];
    tags: string[];
}

export interface Extraction {
    is_resume?: boolean;
    validity_confidence?: number;
    validity_reason?: string;
    contact: Contact;
    education: EducationEntry[];
    experience: ExperienceEntry[];
    projects: ProjectEntry[];
    technical_skills: string[];
    awards: string[];
    certificates: string[];
    calculated_yoe: number | null;
    concerns: string[];
    custom?: Record<string, unknown>;
}

export type MatchTier = 'Excellent' | 'Good' | 'Average' | 'Bad';

export type ResumeStatus =
    | 'Ready'
    | 'Recruiter-Call'
    | 'Round 1'
    | 'Round 2'
    | 'Final Round'
    | 'Rejected'
    | 'Awaiting Acceptance'
    | 'Accepted';

export const RESUME_STATUSES: ResumeStatus[] = [
    'Ready',
    'Recruiter-Call',
    'Round 1',
    'Round 2',
    'Final Round',
    'Rejected',
    'Awaiting Acceptance',
    'Accepted',
];

export const MATCH_TIERS: MatchTier[] = [
    'Excellent',
    'Good',
    'Average',
    'Bad',
];

export interface Resume {
    id: number;
    filename: string;
    mime_type: string;
    is_resume: boolean;
    validity_confidence: number;
    validity_reason: string;
    extraction: Extraction;
    extraction_raw: Extraction;
    score: number | null;
    match_tier: MatchTier | null;
    scored_against_jd_id: number | null;
    status: ResumeStatus;
    task_id?: string | null;
    processing_status?: 'queued' | 'processing' | 'done' | 'error' | null;
    processing_step?: string | null;
    processing_error?: string | null;
    is_rejected: boolean;
    rejection_reason: string | null;
    subscores: {
        skills?: number;
        experience?: number;
        education?: number;
    } | null;
    rationale: string | null;
}

export interface ResumeListResponse {
    items: Resume[];
    total: number;
    limit: number;
    offset: number;
}

export interface JD {
    id: number;
    title: string;
    body_md: string;
    required_skills: string[];
    created_at: string | null;
    updated_at: string | null;
}

export interface JDSummary {
    id: number;
    title: string;
    created_at: string | null;
    updated_at: string | null;
}

export interface UploadAccepted {
    task_id: string;
    resume_id: number;
    status: 'queued' | 'processing' | 'done' | 'error';
    step: string;
}

export interface ResumeTask {
    task_id: string;
    resume_id: number;
    status: 'queued' | 'processing' | 'done' | 'error';
    step: string;
    error: string | null;
    resume: Resume | null;
}

export interface Alias {
    alias: string;
    kind: string;
    canonical: string;
    source: string;
    frequency: number;
}

export interface CustomField {
    id: number;
    name: string;
    description: string;
    type: 'text' | 'bool' | 'list' | 'number';
}

export interface DashboardStats {
    total: number;
    top_skills: { skill: string; count: number }[];
    yoe_buckets: { bucket: string; count: number }[];
    score_histogram: { bucket: string; count: number }[];
}

async function json<T>(r: Response): Promise<T> {
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<T>;
}

export const api = {
    health: () =>
        fetch('/api/health').then((r) =>
            json<{ ok: boolean; model: string }>(r),
        ),

    listJDs: () => fetch('/api/jd').then((r) => json<JDSummary[]>(r)),
    getJD: (id: number) => fetch(`/api/jd/${id}`).then((r) => json<JD>(r)),
    createJD: (body: {
        title: string;
        body_md: string;
        required_skills: string[];
    }) =>
        fetch('/api/jd', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then((r) => json<JD>(r)),
    updateJD: (
        id: number,
        body: { title: string; body_md: string; required_skills: string[] },
    ) =>
        fetch(`/api/jd/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then((r) => json<JD>(r)),
    deleteJD: (id: number) =>
        fetch(`/api/jd/${id}`, { method: 'DELETE' }).then((r) =>
            json<{ ok: boolean; deleted_resumes: number }>(r),
        ),

    listResumes: (params: {
        jdId?: number | null;
        status?: string | null;
        tier?: string | null;
        limit?: number;
        offset?: number;
    } = {}) => {
        const q = new URLSearchParams();
        if (params.jdId != null) q.set('jd_id', String(params.jdId));
        if (params.status) q.set('status_filter', params.status);
        if (params.tier) q.set('tier', params.tier);
        if (params.limit != null) q.set('limit', String(params.limit));
        if (params.offset != null) q.set('offset', String(params.offset));
        const qs = q.toString();
        return fetch('/api/resumes' + (qs ? `?${qs}` : '')).then((r) =>
            json<ResumeListResponse>(r),
        );
    },
    getResume: (id: number) =>
        fetch(`/api/resumes/${id}`).then((r) => json<Resume>(r)),
    getResumeTask: (taskId: string) =>
        fetch(`/api/resumes/tasks/${taskId}`).then((r) => json<ResumeTask>(r)),
    resumeFileUrl: (id: number) => `/api/resumes/${id}/file`,
    deleteResume: (id: number) =>
        fetch(`/api/resumes/${id}`, { method: 'DELETE' }).then((r) =>
            json<{ ok: boolean }>(r),
        ),
    updateResumeStatus: (id: number, status: ResumeStatus) =>
        fetch(`/api/resumes/${id}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status }),
        }).then((r) => json<Resume>(r)),
    scoreResume: (id: number, jdId: number) =>
        fetch(`/api/resumes/${id}/score`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jd_id: jdId }),
        }).then((r) => json<Resume>(r)),
    retryExtraction: (id: number) =>
        fetch(`/api/resumes/${id}/retry`, { method: 'POST' }).then((r) =>
            json<UploadAccepted>(r),
        ),
    uploadResume: async (file: File, jdId?: number) => {
        const fd = new FormData();
        fd.append('file', file);
        if (jdId != null) {
            fd.append('jd_id', String(jdId));
        }
        const r = await fetch('/api/resumes/upload', {
            method: 'POST',
            body: fd,
        });
        return json<UploadAccepted>(r);
    },
    verifyResume: (
        id: number,
        extraction: Extraction,
        applyAliasLearning = false,
    ) =>
        fetch(`/api/resumes/${id}/verify`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                extraction,
                apply_alias_learning: applyAliasLearning,
            }),
        }).then((r) => json<Resume>(r)),

    listAliases: (kind?: string) =>
        fetch('/api/aliases' + (kind ? `?kind=${kind}` : '')).then((r) =>
            json<Alias[]>(r),
        ),
    upsertAlias: (a: { alias: string; canonical: string; kind?: string }) =>
        fetch('/api/aliases', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(a),
        }).then((r) => json<Alias>(r)),
    deleteAlias: (kind: string, alias: string) =>
        fetch(`/api/aliases/${kind}/${encodeURIComponent(alias)}`, {
            method: 'DELETE',
        }).then((r) => json<{ ok: boolean }>(r)),

    listCustomFields: () =>
        fetch('/api/custom_fields').then((r) => json<CustomField[]>(r)),
    createCustomField: (body: Omit<CustomField, 'id'>) =>
        fetch('/api/custom_fields', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then((r) => json<CustomField>(r)),
    deleteCustomField: (id: number) =>
        fetch(`/api/custom_fields/${id}`, { method: 'DELETE' }).then((r) =>
            json<{ ok: boolean }>(r),
        ),

    stats: () =>
        fetch('/api/dashboard/stats').then((r) => json<DashboardStats>(r)),
};
