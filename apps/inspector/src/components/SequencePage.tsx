import { useMemo, useState } from "react";
import type { HRIComponentProfile } from "@openrois/interfaces";
import type { CommandUnitSequenceItemInput } from "@openrois/sdk";
import { useSession } from "../lib/useSession";
import { errorText } from "../lib/session";
import {
  commandUnitList,
  exampleSequence,
  flatSteps,
  newKey,
  newStep,
  problems,
  runPlan,
  worstStatus,
  type Item,
  type PlanItem,
  type Step,
} from "../lib/sequence";
import { executeSnippet } from "../lib/snippets";
import { Card, CodeBlock, Frame, MethodButton, Pill, Split, Tag, ValueField, clock } from "./ui";

type Update = (step: Step) => void;

function StepEditor({
  step,
  profiles,
  refs,
  problem,
  compact,
  onChange,
  onRemove,
  onMove,
}: {
  step: Step;
  profiles: Record<string, HRIComponentProfile>;
  refs: string[];
  problem?: string;
  compact?: boolean;
  onChange: Update;
  onRemove: () => void;
  onMove?: (delta: number) => void;
}) {
  const commands = profiles[step.ref]?.command_profiles ?? [];
  const message = commands.find((c) => c.name === step.command);
  return (
    <div className={`step${problem ? " has-problem" : ""}`}>
      <div className="step-head">
        <select
          className="select"
          aria-label="Component"
          value={step.ref}
          onChange={(e) => onChange({ ...newStep(e.target.value, profiles[e.target.value]), key: step.key })}
        >
          {refs.map((ref) => (
            <option key={ref}>{ref}</option>
          ))}
        </select>
        {compact ? (
          <button type="button" className="btn btn-ghost btn-small" onClick={onRemove} aria-label="Remove command">
            ✕
          </button>
        ) : (
          <>
            <select
              className="select"
              aria-label="Command"
              value={step.command}
              onChange={(e) => onChange({ ...step, command: e.target.value, args: {} })}
            >
              {commands.map((c) => (
                <option key={c.name}>{c.name}</option>
              ))}
            </select>
            <input
              className="input mono"
              aria-label="Delay in milliseconds"
              placeholder="delay ms"
              value={step.delay}
              onChange={(e) => onChange({ ...step, delay: e.target.value })}
            />
            <span className="row" style={{ flexWrap: "nowrap" }}>
              {onMove && (
                <>
                  <button type="button" className="btn btn-ghost btn-small" onClick={() => onMove(-1)} aria-label="Move up">
                    ↑
                  </button>
                  <button type="button" className="btn btn-ghost btn-small" onClick={() => onMove(1)} aria-label="Move down">
                    ↓
                  </button>
                </>
              )}
              <button type="button" className="btn btn-ghost btn-small" onClick={onRemove} aria-label="Remove command">
                ✕
              </button>
            </span>
          </>
        )}
      </div>
      {compact && (
        <div className="row">
          <select
            className="select"
            aria-label="Command"
            value={step.command}
            onChange={(e) => onChange({ ...step, command: e.target.value, args: {} })}
            style={{ flex: 1 }}
          >
            {commands.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
          <input
            className="input mono"
            aria-label="Delay in milliseconds"
            placeholder="delay ms"
            value={step.delay}
            onChange={(e) => onChange({ ...step, delay: e.target.value })}
            style={{ width: 90 }}
          />
        </div>
      )}
      {(message?.arguments ?? []).length > 0 && (
        <div className="step-args">
          {(message?.arguments ?? []).map((arg) => (
            <ValueField
              key={arg.name}
              profile={arg}
              value={step.args[arg.name] ?? ""}
              onChange={(value) => onChange({ ...step, args: { ...step.args, [arg.name]: value } })}
            />
          ))}
        </div>
      )}
      {problem && <span className="field-help" style={{ color: "var(--ori-warn)" }}>{problem}</span>}
    </div>
  );
}

export function SequencePage({ example = false }: { example?: boolean }) {
  const [session, state] = useSession();
  const profiles = useMemo(() => state.profile?.component_profiles ?? {}, [state.profile]);
  const refs = useMemo(
    () => Object.keys(profiles).filter((ref) => (profiles[ref].command_profiles ?? []).length > 0),
    [profiles],
  );
  const [items, setItems] = useState<Item[]>(() => (example ? exampleSequence(profiles) : []));
  const [plan, setPlan] = useState<PlanItem[] | null>(null);
  const [sentAt, setSentAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const firstRef = refs[0] ?? "";
  const found = problems(items, profiles, state.bound);
  const problemOf = (key: string) => found.find((p) => p.key === key)?.message;

  // The request shows as soon as it can be written. Binds and other problems only block the run.
  let list: CommandUnitSequenceItemInput[] = [];
  try {
    list = commandUnitList(items, profiles);
  } catch {
    list = [];
  }

  const replace = (index: number, item: Item) => setItems((old) => old.map((it, i) => (i === index ? item : it)));
  const remove = (index: number) => setItems((old) => old.filter((_, i) => i !== index));
  const move = (index: number, delta: number) =>
    setItems((old) => {
      const target = index + delta;
      if (target < 0 || target >= old.length) return old;
      const next = [...old];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  const unbound = [...new Set(flatSteps(items).map((s) => s.ref))].filter((ref) => !state.bound.has(ref));

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const ids = await session.execute(
        list,
        flatSteps(items).map((s) => ({ ref: s.ref, type: s.command })),
      );
      setPlan(runPlan(items, ids));
      setSentAt(Date.now());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRunning(false);
    }
  };

  const record = (id: string) => state.commands.find((c) => c.id === id);
  const statusOf = (id: string) => record(id)?.status ?? "RUNNING";
  const request = JSON.stringify(
    { jsonrpc: "2.0", method: "rois.command.execute", params: { command_unit_list: list } },
    null,
    2,
  );

  if (refs.length === 0) {
    return <p className="hint">No component of this engine declares a command.</p>;
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Command Sequence</h1>
          <div className="sub">
            One <Tag>execute</Tag> with commands in order, and concurrent groups whose branches run at the same time.
          </div>
        </div>
        <div className="actions">
          {unbound.length > 0 && (
            <MethodButton
              small={false}
              label={`Bind ${unbound.length === 1 ? unbound[0] : `${unbound.length} Components`}`}
              method="bind"
              onClick={() =>
                void Promise.all(unbound.map((ref) => session.bind(ref))).catch((e) => setError(errorText(e)))
              }
            />
          )}
          <MethodButton
            primary
            small={false}
            label={running ? "Sending" : "Run"}
            method="execute"
            disabled={found.length > 0 || running}
            onClick={run}
          />
        </div>
      </div>
      {error && <p className="message bad">{error}</p>}

      <Split>
        <div className="stack">
          {items.length > 0 && found.length > 0 && (
            <Card title="Before You Run">
              <ul className="hint" style={{ margin: 0, paddingLeft: 18 }}>
                {found.map((p, i) => (
                  <li key={`${p.key}-${i}`}>{p.message}</li>
                ))}
              </ul>
            </Card>
          )}
          <Card
            title="Sequence"
            end={
              <>
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={() => setItems((old) => [...old, { kind: "step", step: newStep(firstRef, profiles[firstRef]) }])}
                >
                  + Command
                </button>
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={() =>
                    setItems((old) => [
                      ...old,
                      {
                        kind: "group",
                        group: {
                          key: newKey(),
                          branches: [[newStep(firstRef, profiles[firstRef])], [newStep(refs[1] ?? firstRef, profiles[refs[1] ?? firstRef])]],
                        },
                      },
                    ])
                  }
                >
                  + Concurrent group
                </button>
              </>
            }
          >
            {items.length === 0 ? (
              <p className="hint">
                Add commands to run one after another, and concurrent groups whose branches run at the same time. The
                next item waits for every branch of a group.
              </p>
            ) : (
              <div className="sequence">
                {items.map((item, index) => (
                  <div className="seq-item" key={item.kind === "step" ? item.step.key : item.group.key}>
                    <span className="seq-index">{index + 1}</span>
                    {item.kind === "step" ? (
                      <StepEditor
                        step={item.step}
                        profiles={profiles}
                        refs={refs}
                        problem={problemOf(item.step.key)}
                        onChange={(step) => replace(index, { kind: "step", step })}
                        onRemove={() => remove(index)}
                        onMove={(delta) => move(index, delta)}
                      />
                    ) : (
                      <div className="group">
                        <div className="group-head">
                          Concurrent group · {item.group.branches.length} branches
                          <span className="end">
                            <button
                              type="button"
                              className="btn btn-small"
                              onClick={() =>
                                replace(index, {
                                  kind: "group",
                                  group: { ...item.group, branches: [...item.group.branches, [newStep(firstRef, profiles[firstRef])]] },
                                })
                              }
                            >
                              + Branch
                            </button>
                            <button type="button" className="btn btn-ghost btn-small" onClick={() => move(index, -1)} aria-label="Move up">
                              ↑
                            </button>
                            <button type="button" className="btn btn-ghost btn-small" onClick={() => move(index, 1)} aria-label="Move down">
                              ↓
                            </button>
                            <button type="button" className="btn btn-ghost btn-small" onClick={() => remove(index)} aria-label="Remove group">
                              ✕
                            </button>
                          </span>
                        </div>
                        {problemOf(item.group.key) && <span className="field-help">{problemOf(item.group.key)}</span>}
                        <div className="branches">
                          {item.group.branches.map((branch, b) => {
                            const setBranch = (next: Step[]) =>
                              replace(index, {
                                kind: "group",
                                group: {
                                  ...item.group,
                                  branches: item.group.branches.map((old, i) => (i === b ? next : old)),
                                },
                              });
                            return (
                              <div className="branch" key={b}>
                                <div className="branch-head">
                                  Branch {b + 1}
                                  <span className="end">
                                    <button
                                      type="button"
                                      className="btn btn-ghost btn-small"
                                      onClick={() => setBranch([...branch, newStep(firstRef, profiles[firstRef])])}
                                    >
                                      + Step
                                    </button>
                                    {item.group.branches.length > 1 && (
                                      <button
                                        type="button"
                                        className="btn btn-ghost btn-small"
                                        aria-label="Remove branch"
                                        onClick={() =>
                                          replace(index, {
                                            kind: "group",
                                            group: { ...item.group, branches: item.group.branches.filter((_, i) => i !== b) },
                                          })
                                        }
                                      >
                                        ✕
                                      </button>
                                    )}
                                  </span>
                                </div>
                                {branch.map((step, s) => (
                                  <StepEditor
                                    key={step.key}
                                    step={step}
                                    profiles={profiles}
                                    refs={refs}
                                    compact
                                    problem={problemOf(step.key)}
                                    onChange={(next) => setBranch(branch.map((old, i) => (i === s ? next : old)))}
                                    onRemove={() => setBranch(branch.filter((_, i) => i !== s))}
                                  />
                                ))}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {found.length > 0 && items.length > 0 && (
              <p className="hint" style={{ marginTop: 12 }}>
                {found.length} {found.length === 1 ? "thing keeps" : "things keep"} the sequence from running.
              </p>
            )}
          </Card>

          <Frame caption="rois.command.execute · request" text={request} />

          <Card title="Last Run" end={sentAt ? <span className="hint">Sent at {clock(sentAt)}</span> : undefined}>
            {!plan ? (
              <p className="hint">
                <Tag>execute</Tag> answers at once with a command id for every command. Each command then ends with{" "}
                <Tag>completed</Tag>, which updates its row here.
              </p>
            ) : (
              <div className="timeline">
                {plan.map((item, i) =>
                  item.kind === "step" ? (
                    <TimelineRow key={item.id} index={`${i + 1}`} step={item.step} id={item.id} record={record(item.id)} />
                  ) : (
                    <div key={item.key} className="group">
                      <div className="group-head">
                        {i + 1}. Concurrent Group
                        <span className="end">
                          <Pill status={worstStatus(item.branches.flat().map((s) => statusOf(s.id)))} />
                        </span>
                      </div>
                      {item.branches.map((branch, b) => (
                        <div key={b} className="timeline">
                          <span className="branch-head">Branch {b + 1}</span>
                          {branch.map(({ step, id }, k) => (
                            <TimelineRow key={id} index={`${i + 1}.${b + 1}.${k + 1}`} step={step} id={id} record={record(id)} />
                          ))}
                        </div>
                      ))}
                    </div>
                  ),
                )}
              </div>
            )}
          </Card>
        </div>
        <CodeBlock code={executeSnippet(list)} />
      </Split>
    </>
  );
}

function TimelineRow({
  index,
  step,
  id,
  record,
}: {
  index: string;
  step: Step;
  id: string;
  record?: { status: string; sentAt: number; endedAt?: number };
}) {
  const status = record?.status ?? "RUNNING";
  return (
    <div className="timeline-row">
      <span className="what">
        <strong>{index}</strong> {step.ref} · <strong>{step.command}</strong> <span className="id mono">{id}</span>
      </span>
      <span className="row">
        {record?.endedAt && <span className="id">{record.endedAt - record.sentAt} ms</span>}
        <Pill status={status} label={status === "RUNNING" ? "Pending" : status} />
      </span>
    </div>
  );
}
