import { PointerEvent as ReactPointerEvent, useRef, useState } from "react";
import { BBox, TemplateRegion } from "../api/client";

interface Props {
  imageUrl: string;
  regions: TemplateRegion[];
  hoveredIndex?: number | null;
  onSelectRegion?: (index: number) => void;
  editableIndex?: number | null;
  onBBoxChange?: (index: number, bbox: BBox) => void;
}

type InteractionMode = "move" | "nw" | "ne" | "sw" | "se";
interface Interaction {
  index: number;
  mode: InteractionMode;
  startX: number;
  startY: number;
  initial: BBox;
  scaleX: number;
  scaleY: number;
  width: number;
  height: number;
  move?: (event: PointerEvent) => void;
  up?: () => void;
}

const MIN_SIZE = 24;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

export default function RegionOverlay({ imageUrl, regions, hoveredIndex, onSelectRegion, editableIndex = null, onBBoxChange }: Props) {
  const [naturalDimensions, setNaturalDimensions] = useState<{ width: number; height: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const interactionRef = useRef<Interaction | null>(null);

  const toImagePoint = (event: PointerEvent | ReactPointerEvent<SVGElement>) => {
    const svg = svgRef.current;
    if (!svg || !naturalDimensions) return { x: 0, y: 0 };
    const bounds = svg.getBoundingClientRect();
    return {
      x: (event.clientX - bounds.left) * naturalDimensions.width / Math.max(bounds.width, 1),
      y: (event.clientY - bounds.top) * naturalDimensions.height / Math.max(bounds.height, 1),
    };
  };

  const stopInteraction = () => {
    const move = interactionRef.current?.move;
    const up = interactionRef.current?.up;
    if (move) window.removeEventListener("pointermove", move);
    if (up) window.removeEventListener("pointerup", up);
    interactionRef.current = null;
  };

  const beginInteraction = (event: ReactPointerEvent<SVGElement>, index: number, mode: InteractionMode) => {
    if (editableIndex !== index || !onBBoxChange || !naturalDimensions) return;
    event.preventDefault();
    event.stopPropagation();
    const region = regions[index];
    if (!region) return;
    const point = toImagePoint(event);
    const svg = svgRef.current;
    if (!svg) return;
    const bounds = svg.getBoundingClientRect();
    const interaction: Interaction & { move?: (moveEvent: PointerEvent) => void; up?: () => void } = {
      index,
      mode,
      startX: point.x,
      startY: point.y,
      initial: { ...region.bbox },
      scaleX: naturalDimensions.width / Math.max(bounds.width, 1),
      scaleY: naturalDimensions.height / Math.max(bounds.height, 1),
      width: naturalDimensions.width,
      height: naturalDimensions.height,
    };
    interaction.move = (moveEvent) => {
      const current = toImagePoint(moveEvent);
      const dx = current.x - interaction.startX;
      const dy = current.y - interaction.startY;
      const initial = interaction.initial;
      let next: BBox = { ...initial };
      if (mode === "move") {
        const width = initial.x2 - initial.x1;
        const height = initial.y2 - initial.y1;
        next.x1 = clamp(initial.x1 + dx, 0, interaction.width - width);
        next.y1 = clamp(initial.y1 + dy, 0, interaction.height - height);
        next.x2 = next.x1 + width;
        next.y2 = next.y1 + height;
      } else {
        if (mode.includes("n")) next.y1 = clamp(initial.y1 + dy, 0, initial.y2 - MIN_SIZE);
        if (mode.includes("s")) next.y2 = clamp(initial.y2 + dy, initial.y1 + MIN_SIZE, interaction.height);
        if (mode.includes("w")) next.x1 = clamp(initial.x1 + dx, 0, initial.x2 - MIN_SIZE);
        if (mode.includes("e")) next.x2 = clamp(initial.x2 + dx, initial.x1 + MIN_SIZE, interaction.width);
      }
      onBBoxChange(index, { x1: Math.round(next.x1), y1: Math.round(next.y1), x2: Math.round(next.x2), y2: Math.round(next.y2) });
    };
    interaction.up = stopInteraction;
    interactionRef.current = interaction;
    window.addEventListener("pointermove", interaction.move);
    window.addEventListener("pointerup", interaction.up, { once: true });
  };

  return <div className="overlay-wrapper">
    <img src={imageUrl} alt="Answer booklet page with detected answer regions" className="overlay-img" onLoad={(event) => setNaturalDimensions({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
    {naturalDimensions && <svg ref={svgRef} viewBox={`0 0 ${naturalDimensions.width} ${naturalDimensions.height}`} className="overlay-svg" role="img" aria-label="Detected answer region overlays">
      {regions.map((region, index) => {
        const { x1, y1, x2, y2 } = region.bbox;
        const width = Math.max(0, x2 - x1);
        const height = Math.max(0, y2 - y1);
        const isHovered = hoveredIndex === index;
        const isEditable = editableIndex === index && Boolean(onBBoxChange);
        const hasQuestion = Boolean(region.question_number?.trim());
        const hasValidBox = width > 0 && height > 0;
        const state = !hasValidBox ? "invalid" : hasQuestion ? "mapped" : "unmapped";
        const labelText = !hasValidBox ? "Invalid region" : hasQuestion ? `Q${region.question_number}${region.part_label ? ` (${region.part_label})` : ""}` : "Unmapped region";
        const colors = state === "mapped" ? { fill: "rgba(37, 99, 235, 0.13)", stroke: "#2563eb", label: "#1d4ed8" } : state === "unmapped" ? { fill: "rgba(217, 119, 6, 0.18)", stroke: "#b45309", label: "#92400e" } : { fill: "rgba(190, 24, 93, 0.18)", stroke: "#be123c", label: "#9f1239" };
        const labelWidth = Math.max(86, labelText.length * 8 + 20);
        const handleSize = Math.max(10, Math.min(18, Math.round(Math.min(width, height) * 0.035)));
        return <g key={`${region.question_number}-${region.part_label}-${index}`} onClick={() => onSelectRegion?.(index)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectRegion?.(index); } }} className={`overlay-region ${isEditable ? "overlay-region-editable" : ""}`} tabIndex={0} role="button" aria-label={`${labelText}, region ${index + 1}`}>
          <rect x={x1} y={y1} width={width} height={height} fill={isHovered || isEditable ? colors.fill.replace("0.", "0.28") : colors.fill} stroke={isHovered || isEditable ? colors.label : colors.stroke} strokeWidth={isHovered || isEditable ? 4 : 2} rx={4} onPointerDown={(event) => beginInteraction(event, index, "move")} />
          <rect x={x1 + 4} y={y1 + 4} width={labelWidth} height={24} fill={isHovered || isEditable ? colors.label : colors.stroke} rx={4} pointerEvents="none" />
          <text x={x1 + 12} y={y1 + 20} fill="white" fontSize={12} fontWeight={700} fontFamily="Inter, sans-serif" pointerEvents="none">{labelText}</text>
          {isEditable && <>
            <circle cx={x1} cy={y1} r={handleSize} className="crop-handle crop-handle-nw" onPointerDown={(event) => beginInteraction(event, index, "nw")} />
            <circle cx={x2} cy={y1} r={handleSize} className="crop-handle crop-handle-ne" onPointerDown={(event) => beginInteraction(event, index, "ne")} />
            <circle cx={x1} cy={y2} r={handleSize} className="crop-handle crop-handle-sw" onPointerDown={(event) => beginInteraction(event, index, "sw")} />
            <circle cx={x2} cy={y2} r={handleSize} className="crop-handle crop-handle-se" onPointerDown={(event) => beginInteraction(event, index, "se")} />
          </>}
        </g>;
      })}
    </svg>}
  </div>;
}
