import { useState } from "react";
import { Check, RotateCcw } from "lucide-react";
import Modal from "../../components/Modal";
import { DEFAULT, defaultOptions, type Options } from "./types";
const FOCUSES = [
  DEFAULT,
  "概念理解",
  "物质性质",
  "化学方程式",
  "实验现象和操作",
  "计算",
];
const GROUPS: [
  keyof Omit<Options, "focus" | "extra">,
  string,
  string[],
  string?,
][] = [
  [
    "duration",
    "用时",
    [DEFAULT, "20 分钟", "30 分钟", "35 分钟", "40 分钟", "45 分钟"],
    "未指定时沿用已有用时，没有已有设置则采用 35 分钟。",
  ],
  [
    "score",
    "满分",
    [DEFAULT, "50 分", "100 分", "150 分"],
    "未指定时沿用已有满分，没有已有设置则采用 100 分。",
  ],
  ["questions", "题型和数量", [DEFAULT, "自动安排"]],
  [
    "difficulty",
    "题目难度",
    [DEFAULT, "基础为主", "基础与应用搭配", "综合提高"],
  ],
  [
    "origin",
    "出题方式",
    [DEFAULT, "只用原题", "允许改编原题", "允许改编和出新题"],
  ],
];
export default function OptimizeDialog({
  chapter,
  value,
  onApply,
  onClose,
}: {
  chapter: string;
  value: Options;
  onApply: (v: Options) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Options>(() => ({
    ...structuredClone(value),
    focus: value.focus.filter((f) => FOCUSES.includes(f)),
  }));
  const [customs, setCustoms] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      GROUPS.map(([key, , items]) => [key, !items.includes(value[key])]),
    ),
  );
  const [customFocus, setCustomFocus] = useState(() =>
    value.focus.some((f) => !FOCUSES.includes(f)),
  );
  const [focusText, setFocusText] = useState(() =>
    value.focus.filter((f) => !FOCUSES.includes(f)).join("、"),
  );
  const invalid =
    GROUPS.some(([key]) => !draft[key].trim()) ||
    (customFocus && !focusText.trim()) ||
    (customs.duration &&
      !/^\d+(?:\.\d+)?\s*(?:分钟)?$/.test(draft.duration.trim())) ||
    (customs.score && !/^\d+(?:\.\d+)?\s*(?:分)?$/.test(draft.score.trim())) ||
    (customs.duration &&
      !(parseFloat(draft.duration) > 0 && parseFloat(draft.duration) <= 180)) ||
    (customs.score &&
      !(parseFloat(draft.score) > 0 && parseFloat(draft.score) <= 1000));
  function toggle(item: string) {
    setDraft((old) => {
      let focus =
        item === DEFAULT
          ? [DEFAULT]
          : old.focus.includes(item)
            ? old.focus.filter((f) => f !== item)
            : [...old.focus.filter((f) => f !== DEFAULT), item];
      if (!focus.length && !customFocus) focus = [DEFAULT];
      return { ...old, focus };
    });
    if (item === DEFAULT) {
      setCustomFocus(false);
      setFocusText("");
    }
  }
  return (
    <Modal title="优化提示" onClose={onClose} className="optimize-modal">
      <div className="modal-scroll">
        <p className="lesson-caption">化学 · 限时练</p>
        <h3 className="lesson-heading">{chapter}</h3>
        <div className="option-grid">
          {GROUPS.map(([key, label, items, hint]) => (
            <fieldset key={key} className="choice-group">
              <legend>{label}</legend>
              <div className="choices">
                {items.map((item) => (
                  <button
                    type="button"
                    key={item}
                    aria-pressed={!customs[key] && draft[key] === item}
                    className={
                      "choice " +
                      (!customs[key] && draft[key] === item ? "selected" : "")
                    }
                    onClick={() => {
                      setCustoms({ ...customs, [key]: false });
                      setDraft({ ...draft, [key]: item });
                    }}
                  >
                    {item}
                  </button>
                ))}
                <button
                  type="button"
                  aria-pressed={!!customs[key]}
                  className={"choice " + (customs[key] ? "selected" : "")}
                  onClick={() => {
                    setCustoms({ ...customs, [key]: true });
                    setDraft({ ...draft, [key]: "" });
                  }}
                >
                  {key === "questions" ? "自己指定" : "自己填写"}
                </button>
              </div>
              {customs[key] && (
                <input
                  aria-label={label + "自定义"}
                  className="custom-input"
                  maxLength={key === "questions" ? 500 : 200}
                  value={draft[key]}
                  placeholder={
                    key === "questions"
                      ? "例如：5 道选择题和 2 道解答题"
                      : `填写${label}`
                  }
                  onChange={(e) =>
                    setDraft({ ...draft, [key]: e.target.value })
                  }
                />
              )}
              {hint && <p className="field-hint">{hint}</p>}
            </fieldset>
          ))}
        </div>
        <fieldset className="focus-group">
          <legend>
            重点练什么 <span>（可多选）</span>
          </legend>
          <div className="choices">
            {FOCUSES.map((item) => (
              <button
                type="button"
                key={item}
                className={
                  "choice check-choice " +
                  (draft.focus.includes(item) ? "selected" : "")
                }
                aria-pressed={draft.focus.includes(item)}
                onClick={() => toggle(item)}
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
                const next = !customFocus;
                setCustomFocus(next);
                setDraft({
                  ...draft,
                  focus: next
                    ? draft.focus.filter((f) => f !== DEFAULT)
                    : draft.focus.filter((f) => FOCUSES.includes(f)).length
                      ? draft.focus.filter((f) => FOCUSES.includes(f))
                      : [DEFAULT],
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
              aria-label="重点自定义"
              maxLength={200}
              value={focusText}
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
            aria-label="补充要求"
            maxLength={3000}
            value={draft.extra}
            placeholder="例如：学生基础较弱，请增加分步提示；只使用教材原题，不加入未学内容。"
            onChange={(e) => setDraft({ ...draft, extra: e.target.value })}
          />
        </label>
      </div>
      <footer className="modal-footer">
        <button
          className="text-button muted"
          onClick={() => {
            setDraft(defaultOptions());
            setCustoms({});
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
            onClick={() =>
              onApply({
                ...draft,
                focus: customFocus
                  ? [
                      ...draft.focus.filter(
                        (f) => f !== DEFAULT && FOCUSES.includes(f),
                      ),
                      focusText.trim(),
                    ]
                  : draft.focus.filter((f) => FOCUSES.includes(f)).length
                    ? draft.focus.filter((f) => FOCUSES.includes(f))
                    : [DEFAULT],
              })
            }
          >
            填入
          </button>
        </div>
      </footer>
    </Modal>
  );
}
