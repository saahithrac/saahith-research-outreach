import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
from urllib.parse import quote

DATA_DIR = Path(__file__).parent / "data"
FACULTY_CSV = DATA_DIR / "faculty_targets.csv"
PROFILE_CSV = DATA_DIR / "student_profile.csv"
DRAFTS_CSV = DATA_DIR / "draft_queue.csv"

INSTITUTIONS = ["UNC Gillings", "Duke Margolis", "NCCU RCMI / RCHDR"]
FIELDS = [
    "All fields",
    "Biostatistics",
    "Epidemiology",
    "Health Policy and Management",
    "Health Behavior",
    "Maternal and Child Health",
    "Environmental / Occupational Health",
    "Nutrition / Population Health",
    "Implementation Science",
    "Health Equity / Disparities",
    "GIS / Spatial Analysis",
    "Community Engagement",
    "Other public health / data science",
]
TARGET_QUOTAS = {
    "UNC Gillings": 50,
    "Duke Margolis": 50,
    "NCCU RCMI / RCHDR": None,  # flexible: use all verified relevant contacts; do not force 50
}

REQUIRED_COLUMNS = [
    "selected", "wave", "priority", "institution", "field_of_study", "name", "title", "email", "department",
    "research_keywords", "recent_work", "paper_1_title", "paper_1_url", "paper_2_title", "paper_2_url",
    "source_url", "verification_status", "fit_notes", "status", "last_contacted", "follow_up_date"
]

st.set_page_config(page_title="Saahith Research Outreach", page_icon="📬", layout="wide")

@st.cache_data(show_spinner=False)
def load_csv(path):
    return pd.read_csv(path).fillna("")

def save_csv(df, path):
    path.parent.mkdir(exist_ok=True)
    df.to_csv(path, index=False)
    st.cache_data.clear()

def ensure_columns(df):
    legacy = {"NCCU RCMI Engagement Core": "NCCU RCMI / RCHDR"}
    if "institution" in df.columns:
        df["institution"] = df["institution"].replace(legacy)
    for c in REQUIRED_COLUMNS:
        if c not in df.columns:
            if c == "selected":
                df[c] = False
            elif c == "wave":
                df[c] = "Wave 1"
            elif c == "priority":
                df[c] = "Medium"
            elif c == "field_of_study":
                df[c] = df.apply(infer_field, axis=1) if len(df) else "Other public health / data science"
            elif c == "verification_status":
                df[c] = df.get("status", "needs_verification")
            else:
                df[c] = ""
    return df[REQUIRED_COLUMNS]

def infer_field(row):
    text = " ".join(str(row.get(c, "")) for c in ["department", "research_keywords", "recent_work", "fit_notes"]).lower()
    if "biostat" in text or "statistical" in text or "survival analysis" in text:
        return "Biostatistics"
    if "epidemi" in text or "population" in text:
        return "Epidemiology"
    if "policy" in text or "payment" in text or "health economics" in text:
        return "Health Policy and Management"
    if "behavior" in text or "communication" in text or "intervention" in text:
        return "Health Behavior"
    if "maternal" in text or "child" in text or "newborn" in text or "pediatric" in text:
        return "Maternal and Child Health"
    if "environment" in text or "occupational" in text:
        return "Environmental / Occupational Health"
    if "gis" in text or "spatial" in text or "geography" in text:
        return "GIS / Spatial Analysis"
    if "community" in text or "engagement" in text or "dispar" in text or "equity" in text:
        return "Health Equity / Disparities"
    return "Other public health / data science"

def normalize_bool(v):
    return str(v).strip().lower() in {"yes", "true", "1", "y", "selected"}

def is_verified_status(v):
    """Return True only for affirmative verification statuses.

    This intentionally does NOT treat values like 'unverified' or
    'needs_verification' as verified just because they contain the letters
    'verified' or 'verification'.
    """
    value = str(v).strip().lower().replace(" ", "_").replace("-", "_")
    affirmative = {
        "verified",
        "source_verified",
        "paper_verified",
        "send_ready",
        "fully_verified",
        "verified_no_paper_reference",
    }
    return value in affirmative or value.startswith("verified_")

def load_profile():
    df = load_csv(PROFILE_CSV)
    return {row["field"]: row["value"] for _, row in df.iterrows()}

def profile_editor(profile):
    st.subheader("1) Student profile")
    st.caption("Fill this once. The draft generator uses these details without making every email sound identical.")
    col1, col2 = st.columns(2)
    with col1:
        profile["student_name"] = st.text_input("Name", profile.get("student_name", "Saahith Rachakonda"))
        profile["grade_school"] = st.text_input("Grade / school", profile.get("grade_school", "rising junior in high school"))
        profile["location"] = st.text_input("Location", profile.get("location", "North Carolina"))
        profile["interests"] = st.text_area("Research interests", profile.get("interests", "health equity research; newborn screening policy disparities; biostatistics, GIS, and epidemiological methods for underserved communities in North Carolina"), height=120)
    with col2:
        profile["skills"] = st.text_area("Skills / tools", profile.get("skills", "spreadsheet organization, literature review, quantitative reasoning, early data analysis exposure; interested in learning R, Python, GIS, epidemiology, and biostatistics"), height=120)
        profile["experiences"] = st.text_area("Experiences to mention", profile.get("experiences", "a week of CF research at UNC Marsico Lung Institute with Dr. Camille Ehre, where I analyzed immunohistochemistry and TEM mouse intestinal biopsy data; Center for People's Forestry communications work around tribal welfare/community health; AMWHO health equity outreach; Science Olympiad mentoring; upcoming glioblastoma research/shadowing"), height=120)
        profile["availability"] = st.text_input("Availability", profile.get("availability", "available after school during the academic year and more flexibly during summer"))
        profile["resume_link"] = st.text_input("Resume / portfolio link", profile.get("resume_link", ""))
    if st.button("Save profile", type="primary"):
        save_csv(pd.DataFrame([{"field": k, "value": v} for k, v in profile.items()]), PROFILE_CSV)
        st.success("Profile saved.")
    return profile

def validate_faculty(df):
    rows = []
    for inst in INSTITUTIONS:
        sub = df[df["institution"] == inst]
        named = sub[(sub["name"].str.strip() != "") & (~sub["name"].str.contains("TBD", case=False, na=False))]
        ready = named[
            (named["email"].str.strip() != "") &
            (named["source_url"].str.strip() != "") &
            (named["verification_status"].apply(is_verified_status)) &
            ((named["paper_1_title"].str.strip() == "") | (named["paper_1_url"].str.strip() != ""))
        ]
        quota = TARGET_QUOTAS[inst]
        rows.append({
            "institution": inst,
            "target": "all verified relevant contacts" if quota is None else quota,
            "rows_in_file": len(sub),
            "named_rows": len(named),
            "send_ready_rows": len(ready),
            "remaining_to_target": "flexible" if quota is None else max(0, quota - len(named)),
        })
    return pd.DataFrame(rows)

def score_fit(row):
    text = " ".join(str(row.get(c, "")) for c in ["field_of_study", "department", "research_keywords", "recent_work", "paper_1_title", "paper_2_title", "fit_notes"]).lower()
    score = 0
    for kw in ["data", "stat", "biostat", "policy", "health", "dispar", "equity", "implementation", "epidemiology", "analytics", "community", "maternal", "child", "gis", "spatial", "underserved"]:
        if kw in text:
            score += 1
    if str(row.get("email", "")).strip():
        score += 2
    if str(row.get("paper_1_title", "")).strip() and str(row.get("paper_1_url", "")).strip():
        score += 3
    if is_verified_status(row.get("verification_status", "")):
        score += 3
    return score

def send_ready(row):
    if not is_verified_status(row.get("verification_status", "")):
        return False
    if str(row.get("name", "")).strip() == "" or "TBD" in str(row.get("name", "")).upper():
        return False
    if not str(row.get("email", "")).strip():
        return False
    if not str(row.get("source_url", "")).strip():
        return False
    if str(row.get("paper_1_title", "")).strip() and not str(row.get("paper_1_url", "")).strip():
        return False
    if str(row.get("paper_2_title", "")).strip() and not str(row.get("paper_2_url", "")).strip():
        return False
    return True

def generate_email(row, profile):
    last = str(row.get("name", "Professor")).replace(", PhD", "").replace(", MD", "").split()[-1].replace(",", "")
    title_blob = (str(row.get("title", "")) + " " + str(row.get("name", ""))).lower()
    honorific = "Dr." if any(x in title_blob for x in ["phd", "md", "dr.", "professor"]) else "Professor"
    greeting = f"Dear {honorific} {last},"
    name = profile.get("student_name", "Saahith Rachakonda")
    grade = profile.get("grade_school", "rising junior in high school")
    interests = profile.get("interests", "health equity research and public health data analysis")
    experiences = profile.get("experiences", "")
    availability = profile.get("availability", "available after school and during summer")
    resume_link = profile.get("resume_link", "")

    inst = str(row.get("institution", "your institution"))
    field = str(row.get("field_of_study", "public health"))
    research = str(row.get("recent_work", "")).strip()
    p1 = str(row.get("paper_1_title", "")).strip()
    p2 = str(row.get("paper_2_title", "")).strip()
    keywords = str(row.get("research_keywords", "")).strip()

    opening = f"My name is {name}, and I am a {grade} in {profile.get('location', 'North Carolina')} interested in {interests}."
    ref_parts = []
    if research:
        ref_parts.append(f"I was drawn to your work on {research}")
    if p1:
        ref_parts.append(f"and your paper/project \"{p1}\"")
    if p2:
        ref_parts.append(f"I also noticed \"{p2}\"")
    if ref_parts:
        ref_sentence = " ".join(ref_parts) + ", because I am trying to learn how rigorous data analysis can be used to study health inequities and improve public health decisions."
    elif keywords:
        ref_sentence = f"I was drawn to your work related to {keywords}, because it connects to my interest in using data analysis to study health inequities and underserved communities."
    else:
        ref_sentence = f"I was drawn to your group’s work in {field}, because it connects to my interest in using data analysis to study public health problems."

    exp_sentence = f"My background includes {experiences}" if experiences else "I am building skills in careful data organization, literature review, and quantitative public health research."
    resume_sentence = f" My resume/portfolio is here: {resume_link}" if resume_link else ""

    subject = "High school student interested in data analysis research"
    body = f"""{greeting}

{opening} {ref_sentence}

I am reaching out because I am seeking a volunteer research internship where I can contribute to a health policy, biostatistics, epidemiology, GIS/spatial analysis, or health equity project. {exp_sentence}. I would be grateful for the chance to help with data organization, literature review, basic analysis, coding, or other entry-level research tasks for your group at {inst}.

I know I am early in my training, but I am reliable, eager to learn, and comfortable doing careful detail-oriented work. I am {availability}. If you are open to it, I would really appreciate the chance to briefly meet or hear whether there might be a project where I could be useful.{resume_sentence}

Thank you for your time and consideration.

Best,
{name}
"""
    return subject, body

def mailto_link(email, subject, body):
    if not email:
        return ""
    return f"mailto:{email}?subject={quote(subject)}&body={quote(body)}"

def faculty_manager(df):
    st.subheader("2) Faculty target database")
    st.caption("UNC Gillings and Duke-Margolis are capped at 50 targets each. NCCU RCMI/RCHDR is flexible: use verified relevant contacts only; do not force 50.")
    st.dataframe(validate_faculty(df), use_container_width=True, hide_index=True)

    with st.expander("Import/export faculty CSV", expanded=False):
        uploaded = st.file_uploader("Upload updated faculty_targets.csv", type=["csv"])
        if uploaded:
            new_df = ensure_columns(pd.read_csv(uploaded).fillna(""))
            save_csv(new_df, FACULTY_CSV)
            st.success("Faculty database updated. Refreshing view.")
            st.rerun()
        st.download_button("Download current faculty_targets.csv", df.to_csv(index=False), "faculty_targets.csv", "text/csv")

    col1, col2, col3, col4 = st.columns([1,1,1,2])
    with col1:
        inst = st.selectbox("University / center", ["All"] + INSTITUTIONS)
    with col2:
        field = st.selectbox("Field of study", FIELDS)
    with col3:
        wave = st.selectbox("Wave", ["All"] + sorted([x for x in df["wave"].unique().tolist() if str(x).strip()]))
    with col4:
        q = st.text_input("Search name, department, keywords, papers, notes")
    hide_placeholders = st.checkbox("Hide placeholder rows", value=True)

    sub = df.copy()
    if inst != "All":
        sub = sub[sub["institution"] == inst]
    if field != "All fields":
        sub = sub[sub["field_of_study"] == field]
    if wave != "All":
        sub = sub[sub["wave"] == wave]
    if q:
        mask = sub.apply(lambda r: q.lower() in " ".join(map(str, r.values)).lower(), axis=1)
        sub = sub[mask]
    if hide_placeholders:
        sub = sub[(sub["name"].str.strip() != "") & (~sub["name"].str.contains("TBD", case=False, na=False))]

    st.dataframe(sub, use_container_width=True, hide_index=True)
    st.info("The filtered table above is view-only. To type into cells, use the editable table below or edit data/faculty_targets.csv in GitHub.")

    with st.expander("Edit faculty database inside the app", expanded=False):
        st.caption("Edit cells here, then click Save edits. For permanent GitHub storage, also download the updated CSV and upload/commit it to data/faculty_targets.csv in GitHub.")
        edited = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "selected": st.column_config.CheckboxColumn("selected"),
                "institution": st.column_config.SelectboxColumn("institution", options=INSTITUTIONS),
                "field_of_study": st.column_config.SelectboxColumn("field_of_study", options=FIELDS[1:]),
                "verification_status": st.column_config.SelectboxColumn(
                    "verification_status",
                    options=[
                        "needs_verification",
                        "verified",
                        "verified_no_paper_reference",
                        "unverified",
                    ],
                ),
                "priority": st.column_config.SelectboxColumn("priority", options=["High", "Medium", "Low"]),
                "wave": st.column_config.SelectboxColumn("wave", options=["Wave 1", "Wave 2", "Wave 3", "Wave 4", "Wave 5", "Hold"]),
                "source_url": st.column_config.LinkColumn("source_url"),
                "paper_1_url": st.column_config.LinkColumn("paper_1_url"),
                "paper_2_url": st.column_config.LinkColumn("paper_2_url"),
            },
            key="faculty_editor",
        )
        edited = ensure_columns(edited.fillna(""))
        c_save, c_download = st.columns(2)
        with c_save:
            if st.button("Save edits in app", type="primary", use_container_width=True):
                save_csv(edited, FACULTY_CSV)
                st.success("Saved in the app. To make it permanent across redeploys, download and commit the CSV to GitHub.")
                st.rerun()
        with c_download:
            st.download_button("Download updated faculty_targets.csv", edited.to_csv(index=False), "faculty_targets.csv", "text/csv", use_container_width=True)

    return df

def draft_workspace(df, profile):
    st.subheader("3) Generate individualized drafts")
    df = df.copy()
    df["fit_score"] = df.apply(score_fit, axis=1)
    df["send_ready"] = df.apply(send_ready, axis=1)
    valid = df[(df["name"].str.strip() != "") & (~df["name"].str.contains("TBD", case=False, na=False))].copy()
    if valid.empty:
        st.warning("No named faculty rows yet. Add verified names, emails, sources, and paper/project details in the database first.")
        return

    colA, colB, colC = st.columns(3)
    with colA:
        inst = st.selectbox("Institution", ["All"] + INSTITUTIONS, key="draft_inst")
    with colB:
        field = st.selectbox("Field", FIELDS, key="draft_field")
    with colC:
        ready_only = st.checkbox("Show send-ready only", value=True)

    valid2 = valid.copy()
    if inst != "All":
        valid2 = valid2[valid2["institution"] == inst]
    if field != "All fields":
        valid2 = valid2[valid2["field_of_study"] == field]
    if ready_only:
        valid2 = valid2[valid2["send_ready"]]
    valid2 = valid2.sort_values(["send_ready", "fit_score", "institution", "field_of_study"], ascending=[False, False, True, True])

    if valid2.empty:
        st.warning("No rows match those filters. Turn off send-ready only, choose another field, or add verification details.")
        return

    col1, col2 = st.columns([1,2])
    with col1:
        name = st.selectbox("Faculty", valid2["name"].tolist())
        row = valid2[valid2["name"] == name].iloc[0].to_dict()
        st.write(f"**Institution:** {row.get('institution','')}")
        st.write(f"**Field:** {row.get('field_of_study','')}")
        st.write(f"**Email:** {row.get('email','') or 'missing'}")
        st.write(f"**Verified:** {row.get('verification_status','')}")
        st.write(f"**Fit score:** {row.get('fit_score','')}")
        if not send_ready(row):
            st.error("Not send-ready yet. Add/verify email, source URL, verification status, and paper URL if a paper is referenced.")
    with col2:
        subject, body = generate_email(row, profile)
        subject = st.text_input("Subject", subject)
        body = st.text_area("Draft body", body, height=450)
        c1, c2, c3 = st.columns(3)
        with c1:
            if send_ready(row) and row.get("email", ""):
                st.link_button("Open in email app", mailto_link(row["email"], subject, body), use_container_width=True)
            elif row.get("email", ""):
                st.button("Not send-ready", disabled=True, use_container_width=True)
            else:
                st.button("Missing email", disabled=True, use_container_width=True)
        with c2:
            if st.button("Add to draft queue", type="primary", use_container_width=True, disabled=not send_ready(row)):
                qdf = load_csv(DRAFTS_CSV) if DRAFTS_CSV.exists() else pd.DataFrame(columns=["date_created","wave","institution","field_of_study","name","email","subject","body","status"])
                qdf.loc[len(qdf)] = [str(date.today()), row.get("wave",""), row.get("institution",""), row.get("field_of_study",""), row.get("name",""), row.get("email",""), subject, body, "drafted_not_sent"]
                save_csv(qdf, DRAFTS_CSV)
                st.success("Added to queue.")
        with c3:
            st.download_button("Download this draft", data=f"Subject: {subject}\n\n{body}", file_name=f"draft_{row.get('name','faculty').replace(' ','_')}.txt", use_container_width=True)

def queue_view():
    st.subheader("4) Draft queue and wave sending")
    if DRAFTS_CSV.exists():
        qdf = load_csv(DRAFTS_CSV)
    else:
        qdf = pd.DataFrame(columns=["date_created","wave","institution","field_of_study","name","email","subject","body","status"])
    st.dataframe(qdf.drop(columns=["body"], errors="ignore"), use_container_width=True, hide_index=True)
    st.download_button("Export queue CSV", qdf.to_csv(index=False), "draft_queue.csv", "text/csv")
    st.info("Recommended: send 10–20 emails per wave, personalize one final sentence manually, and track replies before starting the next wave.")

def main():
    st.title("📬 Saahith Research Outreach Builder")
    st.markdown("A review-first cold outreach tool for health equity, health policy, biostatistics, epidemiology, GIS, and public health data-analysis internships.")
    profile = load_profile()
    df = ensure_columns(load_csv(FACULTY_CSV))
    tab1, tab2, tab3, tab4 = st.tabs(["Profile", "Faculty database", "Draft emails", "Queue/export"])
    with tab1:
        profile_editor(profile)
    with tab2:
        faculty_manager(df)
    with tab3:
        draft_workspace(df, profile)
    with tab4:
        queue_view()

if __name__ == "__main__":
    main()





