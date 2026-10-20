import type { Session, Job, Version } from "../api";
import { formatLessonPrompt } from "../prompt";
import OutlinePreview from "./OutlinePreview";
import { ConversationView, RevisionSuggestions } from "./AgentConversation";
export default function Conversation({
  session,
  job,
  version,
  onVersion,
  onSources,
  onVersionSources,
  onRetry,
  onSuggestion,
  busy,
}: {
  session: Session;
  job?: Job;
  version?: Version;
  onVersion: (id: string) => void;
  onSources: () => void;
  onVersionSources: () => void;
  onRetry: () => void;
  onSuggestion: (v: string) => void;
  busy: boolean;
}) {
  const lastRequest = [...session.messages]
    .reverse()
    .find((m) => m.role === "user");
  return (
    <>
      <ConversationView
        request={formatLessonPrompt(
          lastRequest?.content || "请生成一份导学案。",
          session.settings,
        )}
        product="导学案"
        job={job}
        busy={busy}
        onSources={onSources}
        onRetry={onRetry}
        version={version}
        versions={session.versions.map((v) => ({ ...v, label: v.change_kind }))}
        onVersion={onVersion}
      >
        {version && (
          <OutlinePreview
            version={version}
            sessionId={session.id}
            onSources={onVersionSources}
          />
        )}
      </ConversationView>
      {version && !busy && (
        <RevisionSuggestions
          chapter={session.settings.chapter}
          period={session.settings.period}
          version={version.number}
          items={["精简情境导入", "增加分层练习", "补充易错提醒"]}
          onSuggestion={onSuggestion}
          disabled={version.id !== session.versions.at(-1)?.id}
        />
      )}
    </>
  );
}
