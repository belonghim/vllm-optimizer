import { render, screen } from "@testing-library/react";
import TunerProgressBar from "../TunerProgressBar";

const PHASE_LABELS = {
  applying_config: "설정 업데이트 중...",
  restarting: "서버 재시작 중...",
  waiting_ready: "준비 대기 중...",
  warmup: "워밍업 중...",
  evaluating: "성능 평가 중...",
};

describe("TunerProgressBar", () => {
  const props = {
    isRunning: true,
    trialsCompleted: 5,
    totalTrials: 20,
    currentPhase: { trial_id: 0, phase: "evaluating" }
  };

  it("renders nothing when not running and no trials completed", () => {
    render(<TunerProgressBar isRunning={false} trialsCompleted={0} totalTrials={10} currentPhase={null} />);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("renders progress bar with correct percentage when running", () => {
    render(<TunerProgressBar {...props} />);
    const progressBar = screen.getByRole("progressbar");
    expect(progressBar).toBeInTheDocument();
    expect(progressBar).toHaveStyle("width: 25%");
  });

  it("displays phase label when currentPhase is provided", () => {
    render(<TunerProgressBar {...props} />);
    expect(screen.getByText(/성능 평가 중\.\.\./)).toBeInTheDocument();
  });

  it("shows 100% when all trials are done", () => {
    render(<TunerProgressBar isRunning={false} trialsCompleted={20} totalTrials={20} currentPhase={null} />);
    const progressBar = screen.getByRole("progressbar");
    expect(progressBar).toHaveStyle("width: 100%");
  });

  it("handles edge case: n_trials = 0 (prevent division by zero)", () => {
    render(<TunerProgressBar isRunning={true} trialsCompleted={0} totalTrials={0} currentPhase={null} />);
    const progressBar = screen.getByRole("progressbar");
    expect(progressBar).toHaveStyle("width: 0%");
  });

  it("handles edge case: trialsCompleted > n_trials (capped at 100%)", () => {
    render(<TunerProgressBar isRunning={true} trialsCompleted={25} totalTrials={20} currentPhase={null} />);
    const progressBar = screen.getByRole("progressbar");
    expect(progressBar).toHaveStyle("width: 100%");
  });

  it("updates percentage smoothly on prop changes", () => {
    const { rerender } = render(<TunerProgressBar isRunning={true} trialsCompleted={0} totalTrials={10} currentPhase={null} />);
    let progressBar = screen.getByRole("progressbar");
    expect(progressBar).toHaveStyle("width: 0%");

    rerender(<TunerProgressBar isRunning={true} trialsCompleted={5} totalTrials={10} currentPhase={null} />);
    progressBar = screen.getByRole("progressbar");
    expect(progressBar).toHaveStyle("width: 50%");
  });
});