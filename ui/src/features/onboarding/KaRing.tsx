import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
} from "react";
import type { PartState } from "../../lib/api";
import { approach, arcs, partAlpha, reducedMotion, settleFactor } from "./ring";

/**
 * The onboarding ring: one object that is the Send button, then the Ka ring that reads your
 * input, then the Pending badge. It is mounted in the Shell so it keeps flying across the route
 * change. Phase changes only update `live`; the loop never restarts (living-transitions rule).
 */
type RingMode = "hidden" | "pill" | "ring" | "solid" | "badge";
type RingTarget = {
  mode: RingMode;
  rect?: () => DOMRect | null; // read every frame, so scrolling or resizing never detaches it
  parts?: PartState[];
  label?: string; // drawn inside the badge (the count the real badge will show)
  onArrive?: () => void;
};
type Shape = {
  x: number;
  y: number;
  w: number;
  h: number;
  radius: number;
  fill: number;
  thick: number;
  seg: number;
  breathe: number;
  alpha: number;
};

const K60 = 0.085;
const BUTTON_RADIUS = 10; // matches button.primary border-radius in styles.css
const RING_STROKE = 7;
const BREATH_S = 3.2;

function goal(t: RingTarget, box: DOMRect | null, cur: Shape): Shape {
  if (t.mode === "hidden" || !box)
    return { ...cur, breathe: 0, alpha: t.mode === "hidden" ? 0 : cur.alpha };
  const base = {
    x: box.left + box.width / 2,
    y: box.top + box.height / 2,
    w: box.width,
    h: box.height,
  };
  switch (t.mode) {
    case "pill":
      return {
        ...base,
        radius: BUTTON_RADIUS,
        fill: 1,
        thick: 0,
        seg: 0,
        breathe: 0,
        alpha: 1,
      };
    case "ring":
      return {
        ...base,
        radius: box.width / 2,
        fill: 0,
        thick: RING_STROKE,
        seg: 1,
        breathe: 1,
        alpha: 1,
      };
    case "solid":
      return {
        ...base,
        radius: box.width / 2,
        fill: 0,
        thick: RING_STROKE,
        seg: 0,
        breathe: 0,
        alpha: 1,
      };
    case "badge":
      return {
        ...base,
        radius: box.width / 2,
        fill: 1,
        thick: 0,
        seg: 0,
        breathe: 0,
        alpha: 1,
      };
  }
}

const Ctx = createContext<(t: RingTarget) => void>(() => {});

export function KaRingLayer({ children }: { children: ReactNode }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef<RingTarget>({ mode: "hidden" });
  const shape = useRef<Shape>({
    x: 0,
    y: 0,
    w: 0,
    h: 0,
    radius: 0,
    fill: 0,
    thick: 0,
    seg: 0,
    breathe: 0,
    alpha: 0,
  });
  const arrived = useRef(false);
  const frame = useRef(0);
  const last = useRef(0);
  const colors = useRef({ lapis: "#6384F0", lapisBtn: "#4263D9", at: 0 });
  const tick = useRef<(ms: number) => void>(() => {});

  // The frame function lives in a ref, made once on mount, so set() starts it without re-creating it.
  useEffect(() => {
    tick.current = (ms: number) => {
      const c = canvas.current;
      if (!c) return;
      const ctx = c.getContext("2d")!;
      const dpr = window.devicePixelRatio || 1;
      if (
        c.width !== Math.round(innerWidth * dpr) ||
        c.height !== Math.round(innerHeight * dpr)
      ) {
        c.width = Math.round(innerWidth * dpr);
        c.height = Math.round(innerHeight * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, innerWidth, innerHeight);

      const reduce = reducedMotion();
      const t = live.current;
      const s = shape.current;
      const box = t.rect?.() ?? null;
      const g = goal(t, box, s);
      const k = reduce
        ? 1
        : settleFactor(K60, last.current ? ms - last.current : 1000 / 60);
      last.current = ms;
      for (const key of Object.keys(g) as (keyof Shape)[])
        s[key] = approach(s[key], g[key], k);
      const now = ms / 1000;

      // arrival needs a real target: a missing button or bell must not count as "there"
      if (!arrived.current && t.onArrive && box) {
        const close =
          Math.abs(s.x - g.x) < 1 &&
          Math.abs(s.y - g.y) < 1 &&
          Math.abs(s.w - g.w) < 1 &&
          Math.abs(s.h - g.h) < 1;
        if (close) {
          arrived.current = true;
          t.onArrive();
        }
      }

      if (s.alpha > 0.005) {
        if (ms - colors.current.at > 500) {
          // theme colours: read twice a second, not every frame (getComputedStyle flushes styles)
          const css = getComputedStyle(document.documentElement);
          colors.current = {
            lapis: css.getPropertyValue("--lapis").trim() || "#6384F0",
            lapisBtn: css.getPropertyValue("--lapis-btn").trim() || "#4263D9",
            at: ms,
          };
        }
        const { lapis, lapisBtn } = colors.current;
        const breath = reduce ? 0 : Math.sin((now * 2 * Math.PI) / BREATH_S);
        const b = s.breathe * 0.035 * breath;
        const w = s.w * (1 + b);
        const h = s.h * (1 + b);
        const radius = Math.min(s.radius * (1 + b), w / 2, h / 2);
        ctx.beginPath();
        ctx.roundRect(s.x - w / 2, s.y - h / 2, w, h, radius);
        if (s.fill > 0.01) {
          ctx.globalAlpha = s.alpha * s.fill;
          ctx.fillStyle = lapisBtn;
          ctx.fill();
        }
        if (s.thick > 0.3) {
          ctx.lineWidth = s.thick;
          ctx.strokeStyle = lapis;
          ctx.lineCap = "round";
          // how round the shape is: arcs only make sense on a circle, the outline covers the morph
          const split = s.seg * Math.max(0, 1 - Math.abs(w - h) / 24);
          ctx.globalAlpha = s.alpha * (1 - split);
          ctx.beginPath();
          ctx.roundRect(
            s.x - w / 2 + s.thick / 2,
            s.y - h / 2 + s.thick / 2,
            w - s.thick,
            h - s.thick,
            Math.max(0, radius - s.thick / 2),
          );
          ctx.stroke();
          const parts = t.parts ?? [];
          if (split > 0.01 && parts.length) {
            const r = w / 2 - s.thick / 2;
            arcs(parts.length, parts.length > 1 ? 0.22 * split : 0).forEach(
              (a, i) => {
                ctx.globalAlpha =
                  s.alpha *
                  split *
                  (reduce && parts[i] === "reading"
                    ? 0.8
                    : partAlpha(parts[i], now));
                ctx.beginPath();
                ctx.arc(s.x, s.y, r, a.start, a.end);
                ctx.stroke();
              },
            );
            // a quiet halo pulses with the breath; gated to the round ring so a pill never wears it
            ctx.globalAlpha =
              s.alpha * split * s.breathe * (0.1 + 0.08 * breath);
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(s.x, s.y, w / 2 + 10, 0, Math.PI * 2);
            ctx.stroke();
          }
        }
        if (t.mode === "badge" && t.label && w < 40) {
          ctx.globalAlpha = s.alpha;
          ctx.fillStyle = "#fff";
          ctx.font = "500 12px system-ui, sans-serif"; // matches .badge in styles.css for the hand-over
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(t.label, s.x, s.y + 0.5);
        }
      }
      ctx.globalAlpha = 1;
      const idle = t.mode === "hidden" && s.alpha <= 0.005;
      if (idle) {
        frame.current = 0;
        last.current = 0;
      } else
        frame.current = requestAnimationFrame((next) => tick.current(next));
    };
  }, []);

  const set = useCallback((t: RingTarget) => {
    if (t.onArrive !== live.current.onArrive || t.mode !== live.current.mode)
      arrived.current = false;
    if (
      live.current.mode === "hidden" &&
      shape.current.alpha <= 0.005 &&
      t.mode !== "hidden"
    ) {
      // first appearance: start exactly on the target, so the ring never flies in from (0, 0)
      const box = t.rect?.() ?? null;
      if (box) Object.assign(shape.current, goal(t, box, shape.current));
    }
    live.current = t;
    if (!frame.current)
      frame.current = requestAnimationFrame((ms) => tick.current(ms));
  }, []);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  return (
    <Ctx.Provider value={set}>
      {children}
      <canvas ref={canvas} className="ka-ring-layer" aria-hidden="true" />
    </Ctx.Provider>
  );
}

export const useKaRing = () => useContext(Ctx);
