"use client";

import type { ElementType, ReactNode } from "react";
import { textOf, urduClass } from "@/lib/urdu";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { BACKEND_URL } from "@/lib/api";

type Props = { node?: unknown } & Record<string, unknown>;

// Each block picks its own direction, so Urdu lines read right-to-left
// and English lines left-to-right inside the same answer.
function withAutoDir(Tag: ElementType) {
  return function AutoDir({ node, className, ...props }: Props) {
    void node;
    const urdu = urduClass(textOf(props.children as ReactNode));
    return <Tag dir="auto" className={[className, urdu].filter(Boolean).join(" ") || undefined} {...props} />;
  };
}

function Link({ node, ...props }: Props) {
  void node;
  const href = typeof props.href === "string" && /^\/api\/files\/\d+\/download$/.test(props.href)
    ? BACKEND_URL + props.href : props.href as string | undefined;
  return <a {...props} href={href} target="_blank" rel="noopener noreferrer" />;
}

const components = {
  p: withAutoDir("p"),
  li: withAutoDir("li"),
  h1: withAutoDir("h1"),
  h2: withAutoDir("h2"),
  h3: withAutoDir("h3"),
  blockquote: withAutoDir("blockquote"),
  td: withAutoDir("td"),
  th: withAutoDir("th"),
  a: Link,
} as Components;

export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {text}
    </ReactMarkdown>
  );
}
