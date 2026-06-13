import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowRight, Cpu, Database, Sparkles, Zap } from "lucide-react";

import { cn } from "@/lib/utils";

type SplashScreenProps = {
  onExitStart: () => void;
  onComplete: () => void;
};

const BOOT_LINES = [
  { text: "initializing agent graph", delay: 200 },
  { text: "connecting vector store", delay: 550 },
  { text: "loading workspace index", delay: 900 },
  { text: "ready", delay: 1250 },
] as const;

const EXIT_MS = 900;

function useSplashFitScale(deps: unknown[]) {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  const fit = useCallback(() => {
    const container = containerRef.current;
    const content = contentRef.current;
    if (!container || !content) return;

    content.style.transform = "scale(1)";
    const pad = 16;
    const availableH = container.clientHeight - pad;
    const availableW = container.clientWidth - pad;
    const contentH = content.scrollHeight;
    const contentW = content.scrollWidth;

    const next = Math.min(1, availableH / contentH, availableW / contentW);
    setScale(Number(next.toFixed(3)));
  }, []);

  useLayoutEffect(() => {
    fit();
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(fit);
    observer.observe(container);
    window.addEventListener("resize", fit);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", fit);
    };
    // Re-measure when boot lines / button state changes content height.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fit, ...deps]);

  return { containerRef, contentRef, scale };
}

export function SplashScreen({ onExitStart, onComplete }: SplashScreenProps) {
  const [phase, setPhase] = useState<"enter" | "hold" | "exit">("enter");
  const [visibleLines, setVisibleLines] = useState(0);

  const isReady = visibleLines >= BOOT_LINES.length;
  const { containerRef, contentRef, scale } = useSplashFitScale([
    visibleLines,
    isReady,
    phase,
  ]);

  const beginExit = useCallback(() => {
    if (!isReady) return;
    setPhase((current) => {
      if (current === "exit") return current;
      onExitStart();
      return "exit";
    });
  }, [isReady, onExitStart]);

  useEffect(() => {
    const enterTimer = window.setTimeout(() => setPhase("hold"), 350);
    return () => window.clearTimeout(enterTimer);
  }, []);

  useEffect(() => {
    const timers = BOOT_LINES.map((line, index) =>
      window.setTimeout(() => setVisibleLines(index + 1), line.delay)
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, []);

  useEffect(() => {
    if (phase !== "exit") return;

    const done = window.setTimeout(onComplete, EXIT_MS);
    return () => window.clearTimeout(done);
  }, [phase, onComplete]);

  const progress = isReady
    ? 100
    : Math.round((visibleLines / BOOT_LINES.length) * 85);

  return (
    <div
      className={cn(
        "splash-screen fixed inset-0 z-[100] h-[100dvh] w-full bg-[#05070d] text-white",
        phase === "enter" && "splash-screen-enter",
        phase === "hold" && "splash-screen-visible",
        phase === "exit" && "splash-screen-exit"
      )}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="splash-grid absolute inset-0 opacity-40" aria-hidden />
        <div className="splash-orb splash-orb-a absolute" aria-hidden />
        <div className="splash-orb splash-orb-b absolute" aria-hidden />
        <div className="splash-scanline absolute inset-0" aria-hidden />
      </div>

      <div
        ref={containerRef}
        className="relative z-10 flex h-full w-full items-center justify-center overflow-hidden p-4"
      >
        <div
          ref={contentRef}
          style={{ transform: `scale(${scale})` }}
          className="splash-fit-content flex w-full max-w-xl flex-col items-center text-center"
        >
          <div className="splash-logo-ring mb-5 flex size-20 items-center justify-center rounded-3xl border border-cyan-400/30 bg-cyan-500/10 shadow-[0_0_60px_rgba(34,211,238,0.25)] sm:size-24">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400/20 to-violet-500/20 sm:size-16">
              <Sparkles
                className="size-7 text-cyan-300 sm:size-8"
                strokeWidth={1.5}
              />
            </div>
          </div>

          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.3em] text-cyan-300/80 sm:text-[11px]">
            Personal Intelligence Layer
          </p>
          <h1 className="splash-title text-[clamp(2rem,7vw,3.5rem)] font-semibold tracking-tight text-white">
            Personal<span className="text-cyan-300">Ops</span>
          </h1>
          <p className="mt-2 max-w-md px-2 text-[clamp(0.75rem,2.5vw,0.875rem)] leading-5 text-slate-400 sm:leading-6">
            Local-first AI workspace for study, code, and life — grounded in your
            files, powered by your agent.
          </p>

          <div className="mt-6 w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.03] p-3.5 text-left backdrop-blur-md sm:mt-7 sm:p-4">
            <div className="mb-2.5 flex items-center gap-2 border-b border-white/10 pb-2.5 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">
              <Cpu className="size-3.5 text-cyan-400" />
              System Boot
            </div>

            <ul className="space-y-1.5 font-mono text-[11px] sm:space-y-2 sm:text-xs">
              {BOOT_LINES.map((line, index) => (
                <li
                  key={line.text}
                  className={cn(
                    "flex items-center gap-2 transition-all duration-500",
                    index < visibleLines
                      ? "translate-y-0 opacity-100"
                      : "translate-y-1 opacity-0"
                  )}
                >
                  <span className="text-cyan-400/80">&gt;</span>
                  <span className="text-slate-300">{line.text}</span>
                  {index < visibleLines && (
                    <span className="ml-auto text-emerald-400/90">
                      {index === BOOT_LINES.length - 1 ? "OK" : "ok"}
                    </span>
                  )}
                </li>
              ))}
            </ul>

            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-violet-400 transition-[width] duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-center gap-2 text-[10px] text-slate-500 sm:mt-6 sm:gap-3 sm:text-[11px]">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2.5 py-1 sm:px-3">
              <Database className="size-3 text-cyan-400/80" />
              SQLite + Chroma
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2.5 py-1 sm:px-3">
              <Zap className="size-3 text-violet-400/80" />
              LangGraph Agent
            </span>
          </div>

          <button
            type="button"
            onClick={beginExit}
            disabled={!isReady || phase === "exit"}
            className={cn(
              "mt-5 inline-flex h-10 items-center gap-2 rounded-full border px-8 text-sm font-semibold tracking-wide transition-all outline-none sm:mt-6 sm:h-11 sm:px-10",
              isReady
                ? "cursor-pointer border-cyan-400/50 bg-cyan-500/15 text-cyan-50 shadow-[0_0_32px_rgba(34,211,238,0.2)] hover:border-cyan-300/70 hover:bg-cyan-500/25 hover:shadow-[0_0_48px_rgba(34,211,238,0.32)]"
                : "cursor-not-allowed border-white/10 bg-white/5 text-slate-500 opacity-60"
            )}
          >
            {isReady ? "Start" : "Starting..."}
            <ArrowRight className={cn("size-4", isReady && "text-cyan-300")} />
          </button>
        </div>
      </div>
    </div>
  );
}
