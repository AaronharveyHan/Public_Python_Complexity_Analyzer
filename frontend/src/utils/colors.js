export const riskColor = (score) => {
  if (score < 20) return "#22c55e";
  if (score < 40) return "#84cc16";
  if (score < 60) return "#eab308";
  if (score < 80) return "#f97316";
  return "#ef4444";
};

export const ccColor = (cc) => {
  if (cc <= 5)  return "#22c55e";
  if (cc <= 10) return "#eab308";
  if (cc <= 20) return "#f97316";
  return "#ef4444";
};

export const GRADE_COLOR = {
  A: "#22c55e",
  B: "#84cc16",
  C: "#eab308",
  D: "#f97316",
  F: "#ef4444",
};
