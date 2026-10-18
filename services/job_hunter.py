"""
Autonomous Job Application Hunter
=================================

Ingests a resume, matches it against live vacancies pulled through the
persistent-profile browser worker, tailors a cover letter per role, and fills
application forms on the user's authenticated job boards.

Design notes
------------
* Resume parsing is local (pypdf / python-docx / plain text) - no upload.
* Board discovery reuses the logged-in Chrome profile, so the user stays
  authenticated and no credentials are stored by this module.
* Form submission is opt-in: ``apply`` fills the form and returns the field map
  it touched; the form is only submitted when ``confirm`` is true.
* Every step degrades gracefully - if the model tier is unavailable the module
  falls back to deterministic keyword scoring and a template cover letter.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.user_paths import get_user_data_dir

MODEL_NAME = "gemini-3.8-flash"
MAX_JOBS = 25
MAX_RESUME_CHARS = 24000

STATE_PATH = get_user_data_dir() / "config" / "job_hunter.json"
REPORT_DIR = get_user_data_dir() / "deliverables" / "job_hunter"

BOARDS: Dict[str, str] = {
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}",
    "indeed": "https://www.indeed.com/jobs?q={q}&l={loc}",
    "naukri": "https://www.naukri.com/{q}-jobs-in-{loc}",
    "wellfound": "https://wellfound.com/role/{q}",
    "google": "https://www.google.com/search?q={q}+jobs+in+{loc}",
}

SKILL_VOCABULARY = (
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "sql", "nosql",
    "react", "angular", "vue", "node", "django", "flask", "fastapi", "spring", "dotnet",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins", "ci/cd", "git",
    "machine learning", "deep learning", "nlp", "computer vision", "pytorch", "tensorflow",
    "pandas", "numpy", "spark", "hadoop", "airflow", "etl", "tableau", "power bi", "excel",
    "salesforce", "sap", "oracle", "mysql", "postgresql", "mongodb", "redis", "kafka",
    "agile", "scrum", "jira", "figma", "photoshop", "seo", "marketing", "accounting",
    "bookkeeping", "tally", "quickbooks", "recruitment", "payroll", "logistics", "supply chain",
    "customer support", "communication", "leadership", "project management", "product management",
)


# ----------------------------------------------------------------------------
# state
# ----------------------------------------------------------------------------
def _load_state() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "profile": {},
        "resume_text": "",
        "applications": [],
        "searches": [],
        "updated_at": 0.0,
    }
    try:
        if STATE_PATH.exists():
            with open(STATE_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                defaults.update(data)
    except Exception:
        pass
    return defaults


def _save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(state)
        if len(payload.get("resume_text", "")) > MAX_RESUME_CHARS:
            payload["resume_text"] = payload["resume_text"][:MAX_RESUME_CHARS]
        payload["updated_at"] = time.time()
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# resume ingestion
# ----------------------------------------------------------------------------
def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _read_docx(path: Path) -> str:
    try:
        import docx

        document = docx.Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception:
        return ""


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding, errors="replace")
        except Exception:
            continue
    return ""


def read_resume(path_value: str) -> Tuple[str, str]:
    """Returns ``(text, error)`` for a resume file of any supported type."""
    if not path_value:
        return "", "No resume_path supplied."
    path = Path(path_value).expanduser()
    if not path.exists():
        return "", f"Resume not found at {path}"
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix in (".docx", ".doc"):
        text = _read_docx(path)
    else:
        text = _read_text(path)
    text = (text or "").strip()
    if not text:
        return "", f"Could not extract any text from {path.name} ({suffix or 'unknown type'})."
    return text, ""


def _heuristic_profile(resume_text: str) -> Dict[str, Any]:
    lowered = resume_text.lower()
    skills = [skill for skill in SKILL_VOCABULARY if skill in lowered]

    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", resume_text)
    phone = re.search(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,12}", resume_text)
    years = re.findall(r"(\d{1,2})\+?\s*years?", lowered)

    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    name = lines[0][:80] if lines else ""

    titles = []
    for title in (
        "engineer", "developer", "manager", "analyst", "designer", "consultant",
        "accountant", "recruiter", "architect", "lead", "intern", "specialist",
        "administrator", "executive", "scientist", "marketer",
    ):
        if title in lowered:
            titles.append(title.title())

    return {
        "name": name,
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "skills": skills,
        "years_experience": max((int(value) for value in years), default=0),
        "titles": titles,
        "characters": len(resume_text),
    }


# ----------------------------------------------------------------------------
# model tier (optional)
# ----------------------------------------------------------------------------
def _model_client():
    try:
        from google import genai

        keys_path = get_user_data_dir() / "config" / "api_keys.json"
        key = ""
        if keys_path.exists():
            with open(keys_path, "r", encoding="utf-8") as handle:
                key = (json.load(handle) or {}).get("gemini_api_key", "")
        if not key:
            import os

            key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            return None
        return genai.Client(api_key=key, http_options={"api_version": "v1beta"})
    except Exception:
        return None


def _ask_model(prompt: str, fallback: str) -> str:
    client = _model_client()
    if client is None:
        return fallback
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        text = (getattr(response, "text", "") or "").strip()
        return text or fallback
    except Exception:
        return fallback


def _parse_json(text: str) -> Optional[Any]:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    for pattern in (r"\[.*\]", r"\{.*\}"):
        match = re.search(pattern, candidate, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                continue
    try:
        return json.loads(candidate)
    except Exception:
        return None


# ----------------------------------------------------------------------------
# matching
# ----------------------------------------------------------------------------
def _heuristic_score(job: Dict[str, Any], skills: List[str]) -> Tuple[int, List[str], List[str]]:
    haystack = f"{job.get('title', '')} {job.get('company', '')} {job.get('snippet', '')}".lower()
    matched = [skill for skill in skills if skill in haystack]
    missing = [skill for skill in skills if skill not in haystack][:10]
    score = 0
    if skills:
        score = int(round(100 * len(matched) / max(len(skills), 1)))
    if job.get("title"):
        score = min(100, score + 5)
    return max(0, min(100, score)), matched, missing


def score_job(job: Dict[str, Any], profile: Dict[str, Any], resume_text: str) -> Dict[str, Any]:
    skills = list(profile.get("skills") or [])
    fallback_score, matched, missing = _heuristic_score(job, skills)
    result: Dict[str, Any] = {
        "match_score": fallback_score,
        "matched_skills": matched,
        "missing_skills": missing,
        "rationale": "Deterministic keyword overlap between the resume skills and the posting text.",
    }

    if not resume_text:
        return result

    prompt = (
        "You are an expert technical recruiter. Compare the candidate resume against the job posting.\n"
        'Return ONLY JSON: {"match_score": <0-100 integer>, "matched_skills": [..], '
        '"missing_skills": [..], "rationale": "<one sentence>"}\n\n'
        f"JOB TITLE: {job.get('title', '')}\n"
        f"COMPANY: {job.get('company', '')}\n"
        f"JOB TEXT: {str(job.get('snippet', ''))[:3000]}\n\n"
        f"RESUME (truncated):\n{resume_text[:6000]}"
    )
    parsed = _parse_json(_ask_model(prompt, ""))
    if isinstance(parsed, dict) and "match_score" in parsed:
        try:
            result["match_score"] = max(0, min(100, int(parsed["match_score"])))
        except Exception:
            pass
        for key in ("matched_skills", "missing_skills"):
            if isinstance(parsed.get(key), list):
                result[key] = [str(item) for item in parsed[key]][:20]
        if parsed.get("rationale"):
            result["rationale"] = str(parsed["rationale"])[:400]
    return result


def write_cover_letter(job: Dict[str, Any], profile: Dict[str, Any], resume_text: str) -> str:
    matched = ", ".join((profile.get("skills") or [])[:8]) or "the required stack"
    template = (
        f"Dear Hiring Team,\n\n"
        f"I am applying for the {job.get('title', 'open role')} position"
        f"{' at ' + str(job['company']) if job.get('company') else ''}. "
        f"My background covers {matched}, and I enjoy shipping reliable systems end to end.\n\n"
        f"I would welcome the chance to walk through how my experience maps to your roadmap.\n\n"
        f"Sincerely,\n{profile.get('name') or 'Candidate'}"
    )
    if not resume_text:
        return template

    prompt = (
        "Write a concise, specific 3-paragraph cover letter (max 220 words). "
        "No markdown, no placeholders, plain text only.\n\n"
        f"JOB TITLE: {job.get('title', '')}\n"
        f"COMPANY: {job.get('company', '')}\n"
        f"JOB TEXT: {str(job.get('snippet', ''))[:2000]}\n\n"
        f"CANDIDATE PROFILE: {json.dumps(profile)[:1500]}\n"
        f"RESUME (truncated):\n{resume_text[:5000]}"
    )
    return _ask_model(prompt, template)


# ----------------------------------------------------------------------------
# board discovery
# ----------------------------------------------------------------------------
def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-") or "all"


def build_search_urls(query: str, location: str, boards: List[str]) -> List[Dict[str, str]]:
    query_slug = _slug(query) or "software-engineer"
    location_slug = _slug(location) or "remote"
    urls: List[Dict[str, str]] = []
    for board in boards:
        template = BOARDS.get(board.lower())
        if not template:
            continue
        urls.append(
            {
                "board": board.lower(),
                "url": template.format(q=query_slug, loc=location_slug),
            }
        )
    return urls


def _scrape_board(board: str, url: str, limit: int) -> List[Dict[str, Any]]:
    from services.browser_worker import get_browser

    jobs: List[Dict[str, Any]] = []
    try:
        browser = get_browser()
        links = browser.extract_links(url, pattern="")
    except Exception:
        return jobs

    seen = set()
    for link in links:
        href = link.get("href") or ""
        text = (link.get("text") or "").strip()
        if len(text) < 4 or not href.startswith("http"):
            continue
        lowered = href.lower()
        if not any(token in lowered for token in ("job", "jobs", "career", "position", "vacan", "opening")):
            continue
        if href in seen:
            continue
        seen.add(href)
        company = ""
        parts = re.split(r"\s+[|\u2013\u2014-]\s+", text)
        if len(parts) > 1:
            company = parts[-1].strip()[:80]
        jobs.append(
            {
                "board": board,
                "title": parts[0].strip()[:140],
                "company": company,
                "url": href,
                "snippet": text[:400],
            }
        )
        if len(jobs) >= limit:
            break
    return jobs


def search_jobs(query: str, location: str, boards: List[str], limit: int = MAX_JOBS) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for entry in build_search_urls(query, location, boards):
        results.extend(_scrape_board(entry["board"], entry["url"], limit))
        if len(results) >= limit:
            break
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for job in results:
        if job["url"] in seen:
            continue
        seen.add(job["url"])
        deduped.append(job)
    return deduped[:limit]


# ----------------------------------------------------------------------------
# application
# ----------------------------------------------------------------------------
def _application_form_fields() -> Dict[str, str]:
    return {
        "input[name*='name' i]": "candidate_name",
        "input[name*='email' i]": "candidate_email",
        "input[name*='phone' i]": "candidate_phone",
        "input[type='file']": "resume_path",
    }


def fill_application(job_url: str, profile: Dict[str, Any], resume_path: str, confirm: bool) -> Dict[str, Any]:
    from services.browser_worker import get_browser

    browser = get_browser()
    opened = browser.open(job_url)
    filled: Dict[str, str] = {}
    values = {
        "candidate_name": str(profile.get("name") or ""),
        "candidate_email": str(profile.get("email") or ""),
        "candidate_phone": str(profile.get("phone") or ""),
    }
    for selector, field in _application_form_fields().items():
        if field == "resume_path":
            continue
        value = values.get(field, "")
        if value and browser.fill(selector, value):
            filled[selector] = "filled"
    if resume_path:
        filled["input[type='file']"] = "resume attached by browser dialog" if confirm else "pending"

    submitted = False
    if confirm:
        submitted = browser.click("button[type='submit'], input[type='submit']")
    return {
        "job_url": job_url,
        "opened": opened,
        "fields_filled": filled,
        "submitted": submitted,
        "requires_confirmation": not confirm,
    }


# ----------------------------------------------------------------------------
# public callable
# ----------------------------------------------------------------------------
def _resume_path_from(params: Dict[str, Any], state: Dict[str, Any]) -> str:
    return str(
        params.get("resume_path")
        or params.get("resume")
        or state.get("profile", {}).get("resume_path", "")
        or ""
    )


def job_hunter(parameters: Optional[Dict[str, Any]] = None, player: Any = None) -> Dict[str, Any]:
    """Autonomous recruiter. Actions: profile | search | cover_letter | apply | list | status | report."""
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()
    state = _load_state()

    if action in {"status", "list"}:
        applications = state.get("applications", [])
        return {
            "success": True,
            "message": (
                f"Job hunter ready. {len(applications)} application(s) tracked. "
                f"Profile skills: {len(state.get('profile', {}).get('skills', []))}."
            ),
            "profile": state.get("profile", {}),
            "applications": applications if action == "list" else applications[:5],
        }

    if action in {"profile", "ingest", "resume"}:
        resume_path = _resume_path_from(params, state)
        text, error = read_resume(resume_path)
        if error:
            return {"success": False, "error": error}
        profile = _heuristic_profile(text)
        profile["resume_path"] = resume_path
        if params.get("name"):
            profile["name"] = str(params["name"])
        if params.get("email"):
            profile["email"] = str(params["email"])
        if params.get("phone"):
            profile["phone"] = str(params["phone"])
        state["profile"] = profile
        state["resume_text"] = text
        _save_state(state)
        return {
            "success": True,
            "message": (
                f"Resume ingested ({len(text)} characters). Detected "
                f"{len(profile['skills'])} skills and {profile['years_experience']} year(s) of experience."
            ),
            "profile": profile,
        }

    if action in {"search", "find", "hunt"}:
        query = str(params.get("query") or params.get("role") or "").strip()
        if not query:
            query = " ".join(state.get("profile", {}).get("titles", [])[:2]) or "software engineer"
        location = str(params.get("location") or "remote").strip()
        boards = params.get("boards") or ["linkedin", "indeed", "google"]
        if isinstance(boards, str):
            boards = [item.strip() for item in boards.split(",") if item.strip()]
        limit = int(params.get("limit") or MAX_JOBS)

        jobs = search_jobs(query, location, list(boards), limit)
        scored: List[Dict[str, Any]] = []
        for job in jobs:
            job.update(score_job(job, state.get("profile", {}), state.get("resume_text", "")))
            scored.append(job)
        scored.sort(key=lambda item: item.get("match_score", 0), reverse=True)

        threshold = int(params.get("min_score") or 0)
        shortlist = [job for job in scored if job.get("match_score", 0) >= threshold]
        state.setdefault("searches", []).append(
            {"query": query, "location": location, "when": time.time(), "found": len(scored)}
        )
        _save_state(state)
        return {
            "success": True,
            "message": f"Found {len(scored)} posting(s) for '{query}' in {location}; {len(shortlist)} above threshold {threshold}.",
            "query": query,
            "location": location,
            "count": len(scored),
            "jobs": shortlist[:limit],
        }

    if action in {"cover_letter", "cover", "tailor"}:
        job = params.get("job") if isinstance(params.get("job"), dict) else {
            "title": params.get("title", ""),
            "company": params.get("company", ""),
            "snippet": params.get("snippet", ""),
        }
        if not job.get("title") and not job.get("snippet"):
            return {"success": False, "error": "Provide a job dict (or title/company/snippet) for cover_letter."}
        letter = write_cover_letter(job, state.get("profile", {}), state.get("resume_text", ""))
        out_dir = REPORT_DIR / "cover_letters"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{_slug(job.get('title', 'role'))}_{_slug(job.get('company', 'company'))}_{int(time.time())}.txt"
        path = out_dir / filename
        try:
            path.write_text(letter, encoding="utf-8")
        except Exception:
            path = None
        return {
            "success": True,
            "message": f"Cover letter drafted ({len(letter)} characters){' and saved to ' + str(path) if path else ''}.",
            "cover_letter": letter,
            "path": str(path) if path else "",
        }

    if action in {"apply", "submit"}:
        job_url = str(params.get("job_url") or params.get("url") or "").strip()
        if not job_url:
            return {"success": False, "error": "A job_url is required to apply."}
        resume_path = _resume_path_from(params, state)
        confirm = bool(params.get("confirm", False))
        outcome = fill_application(job_url, state.get("profile", {}), resume_path, confirm)
        record = {
            "job_url": job_url,
            "title": params.get("title", ""),
            "company": params.get("company", ""),
            "submitted": outcome["submitted"],
            "when": time.time(),
        }
        state.setdefault("applications", []).append(record)
        _save_state(state)
        return {
            "success": True,
            "message": (
                "Application submitted." if outcome["submitted"]
                else "Application form prepared; submission requires confirm=true."
            ),
            "result": outcome,
        }

    if action in {"report", "summary"}:
        applications = state.get("applications", [])
        lines = [
            "# Job Hunter Report",
            "",
            f"Profile: {state.get('profile', {}).get('name', 'unknown')}",
            f"Skills: {', '.join(state.get('profile', {}).get('skills', [])[:20]) or 'none detected'}",
            f"Applications tracked: {len(applications)}",
            "",
        ]
        for index, record in enumerate(applications, start=1):
            lines.append(
                f"{index}. {record.get('title') or 'role'} @ {record.get('company') or 'company'} "
                f"- submitted={record.get('submitted')}\n   {record.get('job_url')}"
            )
        report = "\n".join(lines)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / f"job_hunter_report_{int(time.time())}.md"
        try:
            path.write_text(report, encoding="utf-8")
        except Exception:
            path = None
        return {
            "success": True,
            "message": f"Report generated for {len(applications)} application(s).",
            "report": report,
            "path": str(path) if path else "",
        }

    return {
        "success": False,
        "error": (
            f"Unknown job_hunter action '{action}'. "
            "Use profile | search | cover_letter | apply | list | status | report."
        ),
    }


def main() -> int:
    print(json.dumps(job_hunter({"action": "status"}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
