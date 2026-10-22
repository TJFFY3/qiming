/** 【工作台导航】只管理 Agent 切换；各 Agent 的业务状态保留在独立页面中。 */
import { useEffect, useState } from "react";
import StudyGuideAgent from "./agents/study-guide/pages/StudyGuideAgent";
import CoursewareAgent from "./agents/courseware/pages/CoursewareAgent";
import PracticeApp from "./agents/timed-practice/pages/PracticeApp";

type AgentId = "guide" | "courseware" | "practice";
function hashAgent(): AgentId {
  return window.location.hash === "#practice"
    ? "practice"
    : window.location.hash === "#courseware"
      ? "courseware"
      : "guide";
}
export default function App() {
  const [agent, setAgent] = useState<AgentId>(hashAgent);
  const [visited, setVisited] = useState(() => new Set([agent]));
  const selectAgent = (next: AgentId) => {
    setVisited((old) => new Set([...old, next]));
    setAgent(next);
    window.location.hash = next;
  };
  useEffect(() => {
    const navigate = () => {
      const next = hashAgent();
      setVisited((old) => new Set([...old, next]));
      setAgent(next);
    };
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  return (
    <>
      {visited.has("guide") && (
        <div hidden={agent !== "guide"}>
          <StudyGuideAgent
            onCourseware={() => selectAgent("courseware")}
            onPractice={() => selectAgent("practice")}
          />
        </div>
      )}
      {visited.has("courseware") && (
        <div hidden={agent !== "courseware"}>
          <CoursewareAgent
            onGuide={() => selectAgent("guide")}
            onPractice={() => selectAgent("practice")}
          />
        </div>
      )}
      {visited.has("practice") && (
        <div hidden={agent !== "practice"}>
          <PracticeApp onAgentChange={selectAgent} />
        </div>
      )}
    </>
  );
}
