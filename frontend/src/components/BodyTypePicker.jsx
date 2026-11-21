const OPTIONS = [
  { value: 'classic', label: '클래식 (팔 4px)' },
  { value: 'slim', label: '슬림 (팔 3px)' },
];

function BodyTypeIcon({ model }) {
  const armWidth = model === 'slim' ? 6 : 8;
  const leftArmX = 16 - armWidth;

  return (
    <svg
      className="body-type-icon"
      viewBox="0 0 48 64"
      aria-hidden="true"
      shapeRendering="crispEdges"
    >
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      >
        <rect x="16" y="2" width="16" height="16" />
        <rect x="16" y="18" width="16" height="24" />
        <rect x={leftArmX} y="18" width={armWidth} height="24" />
        <rect x="32" y="18" width={armWidth} height="24" />
        <rect x="16" y="42" width="7" height="20" />
        <rect x="25" y="42" width="7" height="20" />
      </g>
    </svg>
  );
}

export default function BodyTypePicker({ value, onChange, disabled = false }) {
  return (
    <fieldset className="body-type-picker">
      <legend className="body-type-legend">스킨 체형</legend>
      <div className="body-type-options">
        {OPTIONS.map((option) => {
          const selected = value === option.value;
          return (
            <label
              key={option.value}
              className={`body-type-option${selected ? ' is-selected' : ''}${disabled ? ' is-disabled' : ''}`}
            >
              <input
                type="radio"
                name="skin-model"
                value={option.value}
                checked={selected}
                disabled={disabled}
                onChange={() => onChange(option.value)}
              />
              <span className="body-type-label">{option.label}</span>
              <BodyTypeIcon model={option.value} />
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
