import type { StudyQuestionType } from "@/lib/api";

export type StudyQuestionTypeCounts = Record<StudyQuestionType, number>;

export const EMPTY_TYPE_COUNTS: StudyQuestionTypeCounts = {
  mcq: 0,
  short_answer: 0,
  calculation: 0,
  true_false: 0,
};

export const DEFAULT_PRACTICE_TYPE_COUNTS: StudyQuestionTypeCounts = {
  mcq: 5,
  short_answer: 5,
  calculation: 0,
  true_false: 0,
};

export const DEFAULT_TEST_TYPE_COUNTS: StudyQuestionTypeCounts = {
  mcq: 5,
  short_answer: 3,
  calculation: 2,
  true_false: 0,
};

export const TYPE_COUNT_FIELDS: Array<{ key: StudyQuestionType; label: string }> = [
  { key: "mcq", label: "Multiple choice" },
  { key: "short_answer", label: "Short answer" },
  { key: "calculation", label: "Calculation" },
  { key: "true_false", label: "True / False" },
];

export function clampTypeCount(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(10, Math.round(value)));
}

export function totalTypeCounts(counts: StudyQuestionTypeCounts): number {
  return counts.mcq + counts.short_answer + counts.calculation + counts.true_false;
}

export function hasAnyTypeCount(counts: StudyQuestionTypeCounts): boolean {
  return totalTypeCounts(counts) > 0;
}

type StudyTypeCountInputsProps = {
  counts: StudyQuestionTypeCounts;
  onChange: (counts: StudyQuestionTypeCounts) => void;
  disabled?: boolean;
};

export function StudyTypeCountInputs({
  counts,
  onChange,
  disabled = false,
}: StudyTypeCountInputsProps) {
  function updateCount(key: StudyQuestionType, raw: string) {
    const next = clampTypeCount(Number(raw) || 0);
    onChange({ ...counts, [key]: next });
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {TYPE_COUNT_FIELDS.map((field) => (
        <label key={field.key} className="space-y-1 text-sm">
          <span className="text-xs font-medium text-muted-foreground">{field.label}</span>
          <input
            type="number"
            min={0}
            max={10}
            value={counts[field.key]}
            disabled={disabled}
            onChange={(event) => updateCount(field.key, event.target.value)}
            className="block w-full rounded-lg border border-border bg-background px-2 py-1.5"
          />
        </label>
      ))}
    </div>
  );
}
