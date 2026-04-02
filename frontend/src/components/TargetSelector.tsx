import { useState, useRef, useEffect } from "react";
import { useClusterConfig } from "../contexts/ClusterConfigContext";
import type { ClusterTarget } from "../types";

interface TargetSelectorProps {
  value?: ClusterTarget | null;
  onChange?: (target: ClusterTarget) => void;
  "data-testid"?: string;
}

interface TargetOption {
  value: string;
  label: string;
  target: ClusterTarget;
  isDefault: boolean;
}

export default function TargetSelector({
  value,
  onChange,
  "data-testid": testId,
}: TargetSelectorProps): React.JSX.Element {
  const { targets } = useClusterConfig();
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const containerRef = useRef<HTMLDivElement>(null);

  const groupedTargets = targets.reduce<Record<string, TargetOption[]>>((acc, target) => {
    const crType = target.crType || "inferenceservice";
    const label = target.isDefault ? `★ ${target.inferenceService}` : target.inferenceService;
    const option: TargetOption = {
      value: `${target.namespace}/${target.inferenceService}/${crType}`,
      label,
      target,
      isDefault: target.isDefault,
    };
    if (!acc[crType]) {
      acc[crType] = [];
    }
    acc[crType].push(option);
    return acc;
  }, {});

  const allOptions = Object.entries(groupedTargets).flatMap(([, options]) => options);
  const selectedValue = value
    ? `${value.namespace}/${value.inferenceService}/${value.crType || "inferenceservice"}`
    : "";

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (option: TargetOption) => {
    onChange?.(option.target);
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (!isOpen) {
      if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
        setIsOpen(true);
        event.preventDefault();
      }
      return;
    }

    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setHighlightedIndex((prev) => (prev < allOptions.length - 1 ? prev + 1 : prev));
        break;
      case "ArrowUp":
        event.preventDefault();
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : prev));
        break;
      case "Enter":
        event.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < allOptions.length) {
          handleSelect(allOptions[highlightedIndex]);
        }
        break;
      case "Escape":
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
    }
  };

  const selectedOption = allOptions.find((opt) => opt.value === selectedValue);

  if (targets.length === 0) {
    return (
      <div className="target-selector target-selector-empty" data-testid={testId}>
        <div className="target-selector-placeholder">No targets available</div>
      </div>
    );
  }

  return (
    <div
      className="target-selector"
      ref={containerRef}
      data-testid={testId}
    >
      <button
        type="button"
        className="target-selector-trigger"
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        data-testid={testId ? `${testId}-trigger` : "target-selector-trigger"}
      >
        <span className="target-selector-value">
          {selectedOption ? (
            <>
              {selectedOption.target.inferenceService}
              <span className="target-selector-ns"> ({selectedOption.target.namespace})</span>
            </>
          ) : (
            <span className="target-selector-placeholder">Select a target</span>
          )}
        </span>
        <span className="target-selector-arrow">{isOpen ? "▲" : "▼"}</span>
      </button>

      {isOpen && (
        <div className="target-selector-dropdown" role="listbox" data-testid={`${testId || "target-selector"}-dropdown`}>
          {Object.entries(groupedTargets).map(([crType, options], groupIndex) => (
            <div key={crType} className="target-selector-group">
              {groupIndex > 0 && <div className="target-selector-divider" />}
              <div className="target-selector-group-header">
                {crType === "inferenceservice" ? "KServe (isvc)" : "LLMIS (llmisvc)"}
              </div>
              {options.map((option, optionIndex) => {
                const globalIndex = allOptions.findIndex((o) => o.value === option.value);
                const isHighlighted = highlightedIndex === globalIndex;
                const isSelected = option.value === selectedValue;
                return (
                  <div
                    key={option.value}
                    className={`target-selector-option ${isHighlighted ? "highlighted" : ""} ${isSelected ? "selected" : ""}`}
                    onClick={() => handleSelect(option)}
                    onMouseEnter={() => setHighlightedIndex(globalIndex)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleSelect(option);
                      }
                    }}
                    role="option"
                    aria-selected={isSelected}
                    tabIndex={0}
                    data-testid={testId ? `${testId}-option-${optionIndex}` : `target-selector-option-${optionIndex}`}
                  >
                    <span className="target-selector-option-star">{option.isDefault ? "★" : ""}</span>
                    <span className="target-selector-option-name">{option.target.inferenceService}</span>
                    <span className="target-selector-option-ns"> ({option.target.namespace})</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
