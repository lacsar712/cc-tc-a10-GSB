<script>
  import { onMount, onDestroy } from "svelte";

  export let session;
  export let onexpire = () => {};

  let snapshots = [];
  let selected = null;
  let windowName = "";
  let error = "";
  let busy = false;
  let timer;

  $: isWriter = session?.role === "writer";

  function authHeaders(extra = {}) {
    return { ...(session ? { Authorization: "Bearer " + session.token } : {}), ...extra };
  }

  async function loadList() {
    const res = await fetch("/api/snapshots", { headers: authHeaders() });
    if (res.status === 401) {
      onexpire();
      return;
    }
    if (res.ok) snapshots = await res.json();
  }

  async function openSnapshot(s) {
    const res = await fetch(`/api/snapshots/${s.id}`, { headers: authHeaders() });
    if (res.status === 401) {
      onexpire();
      return;
    }
    if (res.ok) {
      selected = await res.json();
      error = "";
    }
  }

  async function takeSnapshot() {
    error = "";
    const name = windowName.trim();
    if (!name) {
      error = "请先填通车窗口名称";
      return;
    }
    busy = true;
    try {
      const res = await fetch("/api/snapshots", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ window_name: name }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "快照失败";
        return;
      }
      windowName = "";
      selected = data;
      await loadList();
    } catch {
      error = "点快照时网络异常";
    } finally {
      busy = false;
    }
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    return iso.replace("T", " ").replace(/\.\d+.*$/, "");
  }

  onMount(() => {
    loadList();
    timer = setInterval(loadList, 4000);
  });
  onDestroy(() => clearInterval(timer));
</script>

<style>
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button.secondary { background: #57534e; }
  .err { color: #fb7185; }
  .hint { color: #a8a29e; font-size: 0.85rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  tr.clickable { cursor: pointer; }
  tr.clickable:hover { background: #332e2b; }
  h2 { color: #fbbf24; margin: 0 0 0.5rem; font-size: 1.05rem; }
  .meta { color: #a8a29e; font-size: 0.85rem; margin-bottom: 0.75rem; }
  .ro {
    border: 1px dashed #57534e; border-radius: 6px; padding: 0.6rem 0.8rem;
    color: #a8a29e; font-size: 0.85rem; margin-bottom: 1rem;
  }
</style>

<section>
  <h2>通车窗快照</h2>
  <p class="hint">通车窗打开时点快照，把当时还在路上（待办/在办）的测缝单编号、断面、毫米整份抄进快照库。快照落成后不随后续办结变化。</p>
  {#if isWriter}
    <label for="window-name">通车窗口名称</label>
    <input id="window-name" placeholder="例如 2026-10-06 上午通车窗" bind:value={windowName} />
    <button disabled={busy} on:click={takeSnapshot}>点快照（头与明细一次提交）</button>
    {#if error}<p class="err">{error}</p>{/if}
  {:else}
    <div class="ro">巡检身份可查阅历史快照明细，不能点快照。</div>
  {/if}
</section>

{#if selected}
  <section>
    <h2>快照明细：{selected.window_name}</h2>
    <p class="meta">
      快照编号 #{selected.id} · 点快照人 {selected.created_by} · {fmtTime(selected.created_at)} ·
      在途 {selected.items.length} 笔
      <button class="secondary" style="margin-left:0.5rem" on:click={() => (selected = null)}>收起明细</button>
    </p>
    <table>
      <thead>
        <tr><th>编号</th><th>断面</th><th>毫米</th></tr>
      </thead>
      <tbody>
        {#each selected.items as item}
          <tr>
            <td>{item.log_id}</td>
            <td>{item.chainage}</td>
            <td>{item.delta_mm}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </section>
{/if}

<section>
  <h2>历史快照</h2>
  {#if snapshots.length === 0}
    <p class="hint">还没有任何通车窗快照。</p>
  {:else}
    <table>
      <thead>
        <tr><th>窗口名称</th><th>点快照人</th><th>时间</th><th>在途笔数</th></tr>
      </thead>
      <tbody>
        {#each snapshots as s}
          <tr class="clickable" on:click={() => openSnapshot(s)}>
            <td>{s.window_name}</td>
            <td>{s.created_by}</td>
            <td>{fmtTime(s.created_at)}</td>
            <td>{s.item_count}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>
