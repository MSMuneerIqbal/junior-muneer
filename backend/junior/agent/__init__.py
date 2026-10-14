"""Agents built with the OpenAI Agents SDK."""

from agents import set_tracing_disabled

# Our own audit log records every run. SDK tracing would send copies of chats
# to OpenAI's trace dashboard, so it stays off.
set_tracing_disabled(True)
