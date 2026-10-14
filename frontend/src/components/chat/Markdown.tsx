"use client";

import type { ElementType } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = { node?: unknown } & Record<string, unknown>;

// Each block picks its own direction, so Urdu lines read right-to-left
// and English lines left-to-right inside the same answer.
function withAutoDir(Tag: ElementType) {
  return function AutoDir({ node, ...props }: Props) {
    void node;
    return <Tag dir="auto" {...props} />;
  };
}

function Link({ node, ...props }: Props) {
  void node;
  return <a {...props} target="_blank" rel="noopener noreferrer" />;
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
