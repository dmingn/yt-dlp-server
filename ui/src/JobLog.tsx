import { useLayoutEffect, useRef, useState, type MouseEvent } from "react";

type Props = {
  text: string;
};

export default function JobLog({ text }: Props) {
  const preRef = useRef<HTMLPreElement>(null);
  const shouldFollowLogTailRef = useRef<boolean>(true);
  const [copyLabel, setCopyLabel] = useState<
    "Copy log" | "Copied" | "Copy failed"
  >("Copy log");

  // Poll updates jump to the bottom only while following the tail.
  useLayoutEffect(() => {
    const pre = preRef.current;
    if (!pre) return;
    if (shouldFollowLogTailRef.current) pre.scrollTop = pre.scrollHeight;
  }, [text]);

  function onLogScroll() {
    const pre = preRef.current;
    if (!pre) return;
    shouldFollowLogTailRef.current =
      pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 24;
  }

  async function onCopy(event: MouseEvent) {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopyLabel("Copied");
    } catch {
      setCopyLabel("Copy failed");
    }
    setTimeout(() => setCopyLabel("Copy log"), 1500);
  }

  return (
    <>
      <div className="log-header">
        <button type="button" className="secondary" onClick={onCopy}>
          {copyLabel}
        </button>
      </div>
      <pre ref={preRef} onScroll={onLogScroll}>
        {text}
      </pre>
    </>
  );
}
