"use client";

type Props = {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
};

export function SoundToggle({ enabled, onChange }: Props) {
  return (
    <button
      className="sound-toggle"
      type="button"
      aria-pressed={enabled}
      onClick={() => onChange(!enabled)}
    >
      <span aria-hidden="true">{enabled ? "Sound ON" : "Sound OFF"}</span>
    </button>
  );
}
