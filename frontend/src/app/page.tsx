import { Suspense } from "react";
import { ChatView } from "@/components/chat/ChatView";

export default function ChatPage() {
  // ChatView reads ?c= (the open chat) from the URL, which needs a Suspense boundary.
  return (
    <Suspense>
      <ChatView />
    </Suspense>
  );
}
