import { useState } from "react";
import { TemplateRegion } from "../api/client";

interface Props {
  imageUrl: string;
  regions: TemplateRegion[];
  hoveredIndex?: number | null;
  onSelectRegion?: (index: number) => void;
}

export default function RegionOverlay({ imageUrl, regions, hoveredIndex, onSelectRegion }: Props) {
  const [naturalDimensions, setNaturalDimensions] = useState<{ width: number; height: number } | null>(null);

  return <div className="overlay-wrapper">
    <img src={imageUrl} alt="Blank booklet page with detected answer regions" className="overlay-img" onLoad={(event) => setNaturalDimensions({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
    {naturalDimensions && <svg viewBox={`0 0 ${naturalDimensions.width} ${naturalDimensions.height}`} className="overlay-svg" role="img" aria-label="Detected answer region overlays">
      {regions.map((region, index) => {
        const { x1, y1, x2, y2 } = region.bbox;
        const width = Math.max(0, x2 - x1);
        const height = Math.max(0, y2 - y1);
        const isHovered = hoveredIndex === index;
        const hasQuestion = Boolean(region.question_number?.trim());
        const hasValidBox = width > 0 && height > 0;
        const state = !hasValidBox ? "invalid" : hasQuestion ? "mapped" : "unmapped";
        const labelText = !hasValidBox ? "Invalid region" : hasQuestion ? `Q${region.question_number}${region.part_label ? ` (${region.part_label})` : ""}` : "Unmapped region";
        const colors = state === "mapped" ? { fill: "rgba(37, 99, 235, 0.13)", stroke: "#2563eb", label: "#1d4ed8" } : state === "unmapped" ? { fill: "rgba(217, 119, 6, 0.18)", stroke: "#b45309", label: "#92400e" } : { fill: "rgba(190, 24, 93, 0.18)", stroke: "#be123c", label: "#9f1239" };
        const labelWidth = Math.max(86, labelText.length * 8 + 20);
        return <g key={`${region.question_number}-${region.part_label}-${index}`} onClick={() => onSelectRegion?.(index)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectRegion?.(index); } }} className="overlay-region" tabIndex={0} role="button" aria-label={`${labelText}, region ${index + 1}`}>
          <rect x={x1} y={y1} width={width} height={height} fill={isHovered ? colors.fill.replace("0.", "0.28") : colors.fill} stroke={isHovered ? colors.label : colors.stroke} strokeWidth={isHovered ? 4 : 2} rx={4} />
          <rect x={x1 + 4} y={y1 + 4} width={labelWidth} height={24} fill={isHovered ? colors.label : colors.stroke} rx={4} />
          <text x={x1 + 12} y={y1 + 20} fill="white" fontSize={12} fontWeight={700} fontFamily="Inter, sans-serif">{labelText}</text>
        </g>;
      })}
    </svg>}
  </div>;
}
