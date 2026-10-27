type Slide = { title: string; bullets: string[]; notes: string; source_ids: number[] };
type Source = { id: number; title: string; url: string };
type Presentation = { document: { title: string; slides: Slide[] }; sources: Source[]; slide_count: number };

export function presentationContent(text: string): Presentation | null {
  try {
    const value = JSON.parse(text);
    if (!value || typeof value.document?.title !== "string" || !Number.isInteger(value.slide_count)
      || value.slide_count < 1 || value.slide_count > 24 || !Array.isArray(value.document.slides)
      || value.document.slides.length > 24 || !Array.isArray(value.sources) || value.sources.length > 40) return null;
    if (!value.document.slides.every((slide: Slide) => slide && typeof slide.title === "string"
      && typeof slide.notes === "string" && Array.isArray(slide.bullets) && slide.bullets.every(b => typeof b === "string")
      && Array.isArray(slide.source_ids) && slide.source_ids.every(Number.isInteger))) return null;
    if (!value.sources.every((source: Source) => source && Number.isInteger(source.id)
      && typeof source.title === "string" && typeof source.url === "string" && /^https?:\/\//i.test(source.url))) return null;
    return value;
  } catch { return null; }
}

export function presentationText(text: string): string {
  const deck = presentationContent(text);
  if (!deck) return "Presentation content could not be read.";
  return [deck.document.title, ...deck.document.slides.map((slide, i) =>
    `${i + 1}. ${slide.title}\n${slide.bullets.join("\n")}\n${slide.notes}`), "Sources",
    ...deck.sources.map(source => `[${source.id}] ${source.title}: ${source.url}`)].join("\n\n");
}

export function PresentationReview({ text }: { text: string }) {
  const deck = presentationContent(text);
  if (!deck) return <p className="text-sm text-danger">The presentation cannot be previewed. Reject it and ask Junior for a new draft.</p>;
  return <section aria-label="Presentation review" className="space-y-2 text-sm">
    <p>{deck.slide_count} slides{deck.slide_count > 1 ? ", including a final sources slide" : ""}. Open each slide to review its content.</p>
    <div className="max-h-96 space-y-2 overflow-y-auto">
      {deck.document.slides.map((slide, i) => <details key={i} className="rounded-lg border border-line p-2">
        <summary className="cursor-pointer break-words font-medium">{i + 1}. {slide.title}</summary>
        <ul className="my-2 list-disc space-y-1 pl-5">{slide.bullets.map((bullet, n) => <li dir="auto" key={n}>{bullet}</li>)}</ul>
        <p className="text-xs text-muted">Sources: {slide.source_ids.map(id => `[${id}]`).join(", ") || "Cover"}</p>
        {slide.notes && <><p className="mt-2 text-xs font-medium">Speaker notes</p><p dir="auto" className="whitespace-pre-wrap break-words text-xs">{slide.notes}</p></>}
      </details>)}
      <details className="rounded-lg border border-line p-2">
        <summary className="cursor-pointer font-medium">Source links</summary>
        <ul className="mt-2 space-y-1">{deck.sources.map(source => <li key={source.id} className="break-words text-xs">
          <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-accent underline">[{source.id}] {source.title}</a>
        </li>)}</ul>
      </details>
    </div>
    <p className="text-xs text-muted">To revise this draft, ask Junior for the changes. Your downloaded PowerPoint is also editable.</p>
  </section>;
}
