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

  return (
    <div style={{ position: "relative", display: "inline-block", maxWidth: "100%", borderRadius: "10px", overflow: "hidden", background: "#0f172a" }}>
      <img
        src={imageUrl}
        alt="Template Page"
        onLoad={(e) => {
          setNaturalDimensions({
            width: e.currentTarget.naturalWidth,
            height: e.currentTarget.naturalHeight,
          });
        }}
        style={{
          display: "block",
          maxWidth: "100%",
          height: "auto",
        }}
      />

      {naturalDimensions && (
        <svg
          viewBox={`0 0 ${naturalDimensions.width} ${naturalDimensions.height}`}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "auto",
          }}
        >
          {regions.map((region, index) => {
            const { x1, y1, x2, y2 } = region.bbox;
            const width = Math.max(0, x2 - x1);
            const height = Math.max(0, y2 - y1);
            const isHovered = hoveredIndex === index;
            const labelText = `Q${region.question_number}${region.part_label ? ` (${region.part_label})` : ""}`;

            return (
              <g
                key={`${region.question_number}-${region.part_label}-${index}`}
                onClick={() => onSelectRegion?.(index)}
                style={{ cursor: "pointer" }}
              >
                {/* Rect Bounding Box */}
                <rect
                  x={x1}
                  y={y1}
                  width={width}
                  height={height}
                  fill={isHovered ? "rgba(99, 102, 241, 0.25)" : "rgba(37, 99, 235, 0.12)"}
                  stroke={isHovered ? "#4f46e5" : "#2563eb"}
                  strokeWidth={isHovered ? 4 : 2}
                  rx={4}
                  ry={4}
                />

                {/* Question Label Badge inside SVG */}
                <rect
                  x={x1 + 4}
                  y={y1 + 4}
                  width={Math.max(60, labelText.length * 10 + 16)}
                  height={24}
                  fill={isHovered ? "#4f46e5" : "#1e40af"}
                  rx={4}
                />
                <text
                  x={x1 + 12}
                  y={y1 + 20}
                  fill="white"
                  fontSize={13}
                  fontWeight={600}
                  fontFamily="Inter, sans-serif"
                >
                  {labelText}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
