interface Props {
  direction: string;
}

const directionStyles: Record<string, string> = {
  positive:
    "bg-emerald-100 text-emerald-800 border border-emerald-200",
  negative:
    "bg-red-100 text-red-800 border border-red-200",
  neutral:
    "bg-gray-100 text-gray-700 border border-gray-200",
};

export function DirectionBadge({ direction }: Props) {
  const style =
    directionStyles[direction.toLowerCase()] ??
    "bg-gray-100 text-gray-700 border border-gray-200";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${style}`}
    >
      {direction}
    </span>
  );
}
