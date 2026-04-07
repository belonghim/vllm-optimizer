import type { PerPodMetricSnapshot } from "../types";
import { fmt } from "../utils/format";

interface ExpandablePodRowProps {
  pods: PerPodMetricSnapshot[];
  parentColor?: string;
}

export default function ExpandablePodRow({ pods, parentColor }: ExpandablePodRowProps) {
  if (pods.length === 0) {
    return null;
  }

  return (
    <tr>
      <td colSpan={13} style={{ padding: 0 }}>
        <table className="monitor-table" style={{ margin: 0 }}>
          <thead>
            <tr>
              <th style={parentColor ? { borderLeftColor: parentColor, borderLeftWidth: '3px', borderLeftStyle: 'solid' } : {}}>Pod Name</th>
              <th>TPS</th>
              <th>RPS</th>
              <th>Running</th>
              <th>Waiting</th>
              <th>KV%</th>
              <th>GPU%</th>
              <th>GPU Mem (GB)</th>
            </tr>
          </thead>
          <tbody>
            {pods.map((pod) => (
              <tr key={pod.pod_name}>
                <td style={parentColor ? { borderLeftColor: parentColor, borderLeftWidth: '3px', borderLeftStyle: 'solid' } : {}}>{pod.pod_name}</td>
                <td>{fmt(pod.tps)}</td>
                <td>{fmt(pod.rps)}</td>
                <td>{fmt(pod.running, 0)}</td>
                <td>{fmt(pod.waiting, 0)}</td>
                <td>{fmt(pod.kv_cache)}</td>
                <td>{fmt(pod.gpu_util)}</td>
                <td>{fmt(pod.gpu_mem_used, 1)} / {fmt(pod.gpu_mem_total, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </td>
    </tr>
  );
}