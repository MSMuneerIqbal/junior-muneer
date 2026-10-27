---
name: researched_presentation
description: Make researched PowerPoint, Google Slides or PDF presentations, with concise content, citations and speaker notes for editable decks.
for: [junior_muneer, documents_agent]
---
## Steps
1. Preserve the user's topic, audience, language, requested slide count and learning or business purpose. Use reasonable defaults when they only give a topic.
2. Junior calls ask_documents_agent with pptx by default, google_slides only when Google is explicitly requested, or slides_pdf for a PDF deck. It runs research and exports the actual file. Google creation waits for approval and also returns local PowerPoint. Never hand over a script as the finished deck.
3. Inside the Documents Agent, use the supplied research and source catalog. Plan a coherent sequence with definitions, concrete examples, evidence and limits. Do not invent numbers or citations.
4. Give each slide one purpose, a direct title and short bullets. Use comparisons or numbered processes when helpful, and put detail and source links in speaker notes. Keep the exact requested total (1–24), including cover and the final sources slide added by the exporter. Use at most 12 distinct references across the deck. PDF decks have clickable citations but do not include editable speaker notes.
5. Return the structured content to the exporter. The application sends the completed file to the originating chat. External publication, Google creation or changing files on the PC follows existing permissions.
