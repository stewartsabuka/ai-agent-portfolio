export async function askAgent(prompt: string) {
  const res = await fetch("http://localhost:8001/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt })
  });
  return await res.json();
}