"""Research -> write -> check -> export. No model-written programs or arbitrary execution."""
import asyncio
import json
import re

from junior import gate
from junior.audit import audit
from junior.background import progress
from junior.documents.export import export
from junior.documents.limits import retry_read
from junior.documents.schema import DocumentReview, ResearchDocument, validate_document
from junior.files import safe_name, save_received
from junior.websearch import search_for


async def run_documents(context, request: str, output_format: str, slide_count: int) -> str:
    def stage(label, completed):
        context.check_task_limits()
        progress(context.task_id, label, completed, context)
        context.emit({"type": "step", "id": f"document-{completed}", "kind": "team", "status": "done", "label": label})

    stage("Understanding your request", 0)
    # Only the user's request supplies the topic. Read/research results are fenced and cannot change the job.
    findings = []
    for n, focus in enumerate(("overview and authoritative primary sources", "evidence, examples, limitations and recent developments")):
        stage(f"Researching the topic ({n + 1}/2)", 1)
        query = f"{request[:650]} — {focus}"
        findings.append(await retry_read(context, lambda q=query: search_for(context, q)))
    context.check_task_limits()
    sources = [{"id": i, "title": title, "url": url} for i, (url, title) in enumerate(context.research_sources.items(), 1)]
    if not sources:
        raise ValueError("Research returned no verifiable source links. I stopped rather than make an unsourced file. Try again.")

    stage("Writing the researched content", 2)
    content_slides = slide_count - 1 if slide_count > 1 else 1
    brief = (
        f"Request: {request}\nOutput format: {output_format}\nContent slide count: {content_slides}\n"
        "For PowerPoint, produce exactly that many slides, including a cover only if more than one content slide. "
        "The exporter adds one source slide, so do not add one yourself. Each slide needs 1–5 concise bullets, "
        "one clear purpose, speaker notes and source_ids. Use varied points/comparison/steps layouts when meaningful. "
        "Use sections for a full written report. For spreadsheets provide headers and rows, including a Source column "
        "whose value is an exact catalog URL in every row; use no formulas. Do not invent statistics or research findings. "
        "Cite every factual content section and slide using real catalog IDs (numbered from 1). A title-only cover "
        "can leave source_ids empty. Match the requested language and audience. For PowerPoint leave sections, "
        "headers and rows empty. For a written document leave slides, headers and rows empty.\n\n"
        + gate.fence(context, json.dumps(sources, ensure_ascii=False), "verified search citation catalog")
        + "\n" + gate.fence(context, "\n\n".join(findings)[:26000], "research findings")
    )
    if context.paste:
        brief += "\n" + gate.fence(context, context.paste.get("text", "")[:12000], "the user's pasted source material")
    doc = await retry_read(context, lambda: context.helpers.run_structured("documents_agent", brief, context, ResearchDocument))
    while True:
        stage("Checking facts, citations and content", 3)
        issues = []
        try:
            validate_document(doc, sources, output_format, slide_count)
        except ValueError as e:
            issues.append(str(e))
        if not issues:
            review_prompt = (
                f"Check this {output_format} STRUCTURED CONTENT before export against the request and research. Request: {request}\n"
                f"Expected content slides: {content_slides}. Final exported slide count: {slide_count}. "
                "The exporter adds the final sources slide when the total is greater than one. Do not reject for "
                "a missing attachment or sources slide at this pre-export stage. You are checking content only. "
                "Reject invented facts, unsupported numbers, incorrect explanations, topic drift and dense slides. "
                "Source IDs must support the specific associated claims. Distinguish general advice from facts. "
                "Return passes=true only when it is suitable to deliver.\n"
                + gate.fence(context, "\n".join(findings)[:26000], "research evidence")
                + gate.fence(context, json.dumps(sources, ensure_ascii=False), "source catalog")
                + gate.fence(context, doc.model_dump_json(), "draft to check")
            )
            review = await retry_read(context, lambda: context.helpers.run_structured("documents_checker", review_prompt, context, DocumentReview))
            if not review.passes:
                issues.extend(review.issues or ["The fact checker did not approve this content."])
        if not issues:
            break
        if context.task_retries_used >= context.task_max_retries:
            raise ValueError("The content check did not pass within the retry limit: " + "; ".join(issues)[:700])
        context.task_retries_used += 1
        progress(context.task_id, "Revising after the content check", 3, context)
        fix = brief + "\nFix the following issues and return the complete corrected document:\n" + json.dumps(issues)
        fix += "\n" + gate.fence(context, doc.model_dump_json(), "previous draft")
        doc = await retry_read(context, lambda: context.helpers.run_structured("documents_agent", fix, context, ResearchDocument))

    stage("Building your file", 4)
    data, extension, mime = await asyncio.to_thread(export, doc, sources, output_format, slide_count)
    context.check_task_limits()
    filename = safe_name(re.sub(r"[\[\]()`]", "", doc.title))[:110] + extension
    number, _ = save_received(data, filename, mime, "generated", context.conversation_id)
    context.generated_file_ids.append(number)
    progress(context.task_id, "Returning the finished file", 4, context)
    audit("action", "document_created", detail={"file_id": number, "format": output_format, "sources": len(sources)},
          conversation_id=context.conversation_id)
    result = f"**{doc.title}**\n\n{doc.summary}\n\n[Download {filename}](/api/files/{number}/download)"
    if output_format == "pptx":
        result += f"\n\n{slide_count} editable slides, with source links and speaker notes."
    if output_format in ("google_doc", "google_sheet"):
        from junior.documents.workspace import queue_workspace
        result += "\n\n" + queue_workspace(context, doc, sources, output_format)
    return result
