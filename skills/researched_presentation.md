---
name: researched_presentation
description: Make a PowerPoint presentation or slides on a topic after internet research, with concise editable content, citations and speaker notes.
for: [junior_muneer, documents_agent]
---
## Steps
1. Preserve the user's topic, audience, language, requested slide count and learning or business purpose. Use reasonable defaults when they only give a topic.
2. Junior calls ask_documents_agent with pptx. It runs the research and exports the actual deck. Never hand over a script or ask the user to install software for a deck.
3. Inside the Documents Agent, use the supplied research and source catalog. Plan a coherent sequence with definitions, concrete examples, evidence and limits. Do not invent numbers or citations.
4. Give each slide one purpose, a direct title and short bullets. Use comparisons or numbered processes when helpful, and put detail and source links in speaker notes. Keep the exact requested total, including cover and the final sources slide added by the exporter.
5. Return the structured content to the exporter. The application sends the completed file to the originating chat. External publication, Google creation or changing files on the PC follows existing permissions.
