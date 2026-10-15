import { Children, isValidElement, type ReactNode } from "react";

const URDU = /[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/;

/** True if the text has Urdu (Arabic-script) letters. */
export function hasUrdu(text: string | null | undefined): boolean {
  return !!text && URDU.test(text);
}

/** All the plain text inside some React children (for markdown blocks). */
export function textOf(children: ReactNode): string {
  let out = "";
  Children.forEach(children, (child) => {
    if (typeof child === "string" || typeof child === "number") out += child;
    else if (isValidElement<{ children?: ReactNode }>(child)) out += textOf(child.props.children);
  });
  return out;
}

/** The class that makes Urdu text larger and easier to read (see globals.css). */
export const urduClass = (text: string | null | undefined) => (hasUrdu(text) ? "urdu" : "");
