from datetime import datetime

class ReportBuilder:
    @staticmethod
    def build_markdown_article(title: str, channel: str, video_url: str, analysis: dict) -> str:
        """
        Compiles the structured intelligence analysis into a formatted dossier.
        """
        published_now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        
        takeaways = "\n".join([f"- {t}" for t in analysis.get("key_takeaways", [])])
        topics = ", ".join(analysis.get("topics_covered", []))
        
        entities = analysis.get("entities", {})
        people = ", ".join(entities.get("people", [])) or "None identified"
        orgs = ", ".join(entities.get("organizations", [])) or "None identified"
        locations = ", ".join(entities.get("locations", [])) or "None identified"
        
        upsc = analysis.get("upsc_relevance", {})
        prelims = "\n".join([f"- {p}" for p in upsc.get("prelims_pointers", [])]) or "- General factual coverage"
        mains = "\n".join([f"- {m}" for m in upsc.get("mains_pointers", [])]) or "- General analytical context"
        
        fact_checks = ""
        for fc in analysis.get("fact_check_notes", []):
            fact_checks += f"- **Claim:** {fc.get('claim')}\n  - **Status:** `{fc.get('status')}`\n  - **Details:** {fc.get('details')}\n"
        if not fact_checks:
            fact_checks = "- No high-risk factual anomalies flagged."

        return f"""# {title}

**Source Channel:** {channel} | **Generated:** {published_now}  
**Original Video:** [Watch on YouTube]({video_url})  
**Topics:** {topics}

---

## Executive Summary
{analysis.get('executive_summary', 'No summary provided.')}

---

## Key Intelligence Takeaways
{takeaways}

---

## Competitive Exam & UPSC Perspective
**Syllabus Relevance:** {upsc.get('syllabus_mapping', 'General Studies')}

### Prelims High-Yield Pointers
{prelims}

### Mains Analytical Themes
{mains}

---

## Entities & Context
- **Key Figures:** {people}
- **Organizations / Agencies:** {orgs}
- **Geographic Entities:** {locations}

---

## Fact Verification & Evidentiary Notes
{fact_checks}

---

## Detailed Dossier & Analysis
{analysis.get('deep_dossier_markdown', '')}
"""
