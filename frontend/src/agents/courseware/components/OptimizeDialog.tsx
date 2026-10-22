import { useState } from "react";
import { Check, RotateCcw } from "lucide-react";
import Modal from "../../../components/Modal";
import { DEFAULT, defaultOptions, type CoursewareOptions } from "../domain/types";
const FOCUS = [
  DEFAULT,
  "概念理解",
  "物质性质",
  "化学方程式",
  "实验现象和操作",
  "计算",
];
function Choice({
  label,
  value,
  items,
  onChange,
  customLabel = "自己填写",
  hint,
}: {
  label: string;
  value: string;
  items: string[];
  onChange: (v: string) => void;
  customLabel?: string;
  hint?: string;
}) {
  const custom = !items.includes(value);
  return (
    <fieldset className="choice-group">
      <legend>{label}</legend>
      <div className="choices">
        {items.map((item) => (
          <button
            type="button"
            key={item}
            className={
              "choice " + (!custom && value === item ? "selected" : "")
            }
            aria-pressed={!custom && value === item}
            onClick={() => onChange(item)}
          >
            {item}
          </button>
        ))}
        <button
          type="button"
          className={"choice " + (custom ? "selected" : "")}
          aria-pressed={custom}
          onClick={() => onChange("")}
        >
          {customLabel}
        </button>
      </div>
      {custom && (
        <input
          autoFocus
          className="custom-input"
          aria-label={label + "自定义"}
          maxLength={500}
          placeholder={"填写" + label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {hint && <p className="field-hint">{hint}</p>}
    </fieldset>
  );
}
export default function OptimizeDialog({
  chapter,
  value,
  onApply,
  onClose,
}: {
  chapter: string;
  value: CoursewareOptions;
  onApply: (v: CoursewareOptions) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(() => structuredClone(value));
  const initialCustom = value.focus.find((x) => !FOCUS.includes(x));
  const [customFocus, setCustomFocus] = useState(initialCustom !== undefined),
    [focusText, setFocusText] = useState(initialCustom || "");
  const set = (key: keyof CoursewareOptions, value: string) =>
    setDraft((old) => ({ ...old, [key]: value }));
  const toggle = (item: string) =>
    setDraft((old) => {
      const focus =
        item === DEFAULT
          ? [DEFAULT]
          : old.focus.includes(item)
            ? old.focus.filter((x) => x !== item)
            : [...old.focus.filter((x) => x !== DEFAULT), item];
      return { ...old, focus: focus.length ? focus : [DEFAULT] };
    });
  const invalid =
    [
      draft.scope,
      draft.duration,
      draft.pages,
      draft.exercises,
      draft.teaching,
    ].some((v) => !v.trim()) ||
    (customFocus && !focusText.trim());
  return (
    <Modal title="优化提示" onClose={onClose} className="optimize-modal">
      <div className="modal-scroll">
        <div className="lesson-caption">化学 · PPT</div>
        <h3 className="lesson-heading">{chapter}</h3>
        <div className="option-grid">
          <Choice
            label="教学内容"
            value={draft.scope}
            items={["当前课时（默认）"]}
            customLabel="自定范围"
            onChange={(v) => set("scope", v)}
          />
          <Choice
            label="课堂时长"
            value={draft.duration}
            items={[DEFAULT, "40 分钟", "45 分钟"]}
            onChange={(v) => set("duration", v)}
          />
          <Choice
            label="课件页数"
            value={draft.pages}
            items={[DEFAULT, "自动安排", "10 页", "15 页", "20 页"]}
            onChange={(v) => set("pages", v)}
            hint="指定页数包含封面和结束页，内容放不下时应说明冲突。"
          />
          <Choice
            label="课堂练习"
            value={draft.exercises}
            items={[DEFAULT, "自动安排", "不安排练习"]}
            customLabel="自定练习"
            onChange={(v) => set("exercises", v)}
          />
          <Choice
            label="上课方式"
            value={draft.teaching}
            items={[DEFAULT, "老师讲解为主", "边讲边练", "提问讨论为主"]}
            onChange={(v) => set("teaching", v)}
          />
        </div>
        <fieldset className="focus-group">
          <legend>
            本课重点 <span>（可多选）</span>
          </legend>
          <div className="choices">
            {FOCUS.map((item) => (
              <button
                type="button"
                key={item}
                className={
                  "choice check-choice " +
                  (draft.focus.includes(item) ? "selected" : "")
                }
                aria-pressed={draft.focus.includes(item)}
                onClick={() => {
                  if (item === DEFAULT) {
                    setCustomFocus(false);
                    setFocusText("");
                  }
                  toggle(item);
                }}
              >
                <span
                  className={
                    "checkbox " + (draft.focus.includes(item) ? "checked" : "")
                  }
                >
                  {draft.focus.includes(item) && <Check size={16} />}
                </span>
                {item}
              </button>
            ))}
            <button
              type="button"
              className={
                "choice check-choice " + (customFocus ? "selected" : "")
              }
              aria-pressed={customFocus}
              onClick={() => {
                const enabling = !customFocus;
                setCustomFocus(enabling);
                setDraft((old) => {
                  const focus = old.focus.filter(
                    (x) => FOCUS.includes(x) && x !== DEFAULT,
                  );
                  return {
                    ...old,
                    focus: focus.length || enabling ? focus : [DEFAULT],
                  };
                });
              }}
            >
              <span className={"checkbox " + (customFocus ? "checked" : "")}>
                {customFocus && <Check size={16} />}
              </span>
              自己填写
            </button>
          </div>
          {customFocus && (
            <input
              className="custom-input"
              aria-label="本课重点自定义"
              maxLength={200}
              value={focusText}
              placeholder="填写希望加强的内容"
              onChange={(e) => setFocusText(e.target.value)}
            />
          )}
          <p className="field-hint">
            选择重点只表示加强它，不会自动删除其他必学内容。
          </p>
        </fieldset>
        <label className="extra-field">
          补充要求 <span>（选填）</span>
          <textarea
            maxLength={3000}
            value={draft.extra}
            onChange={(e) => set("extra", e.target.value)}
            placeholder="例如：学生基础较弱，请增加分步提示；只使用教材原题，不加入未学内容。"
          />
        </label>
      </div>
      <footer className="modal-footer">
        <button
          className="text-button muted"
          onClick={() => {
            setDraft(defaultOptions());
            setCustomFocus(false);
            setFocusText("");
          }}
        >
          <RotateCcw size={18} />
          清除全部设置
        </button>
        <div>
          <button className="button secondary" onClick={onClose}>
            取消
          </button>
          <button
            className="button dark"
            disabled={invalid}
            onClick={() => {
              const focus = [
                ...draft.focus.filter(
                  (x) => FOCUS.includes(x) && !(customFocus && x === DEFAULT),
                ),
                ...(customFocus ? [focusText.trim()] : []),
              ];
              onApply({
                ...draft,
                focus: focus.length ? [...new Set(focus)] : [DEFAULT],
              });
            }}
          >
            填入
          </button>
        </div>
      </footer>
    </Modal>
  );
}
