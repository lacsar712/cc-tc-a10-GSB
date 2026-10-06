<script>
  let session = null;
  let logs = [];
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let error = "";
  let loading = false;
  let timer;

  // 通车快照专页
  let view = "desk"; // desk = 在线台账；snap = 通车快照
  let snapshots = [];
  let currentSnap = null;
  let windowName = "";
  let snapError = "";
  let snapLoading = false;

  $: isWriter = session?.role === "writer";

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refresh() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) logs = await res.json();
    if (view === "snap") loadSnapshots();
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    view = "desk";
    snapshots = [];
    currentSnap = null;
    snapError = "";
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  function showDesk() {
    view = "desk";
  }

  function showSnap() {
    view = "snap";
    snapError = "";
    loadSnapshots();
  }

  async function loadSnapshots() {
    if (!session) return;
    const res = await fetch("/api/snapshots", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) snapshots = await res.json();
  }

  async function openSnapshot(id) {
    snapError = "";
    const res = await fetch("/api/snapshots/" + id, { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    const data = await res.json();
    if (!res.ok) {
      snapError = data.detail || "读取快照失败";
      return;
    }
    currentSnap = data;
  }

  async function takeSnapshot() {
    snapError = "";
    if (!windowName.trim()) {
      snapError = "请填写窗口名称";
      return;
    }
    snapLoading = true;
    try {
      const res = await fetch("/api/snapshots", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ window_name: windowName.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        snapError = data.detail || "拍快照失败";
        return;
      }
      windowName = "";
      await loadSnapshots();
      currentSnap = data;
    } catch {
      snapError = "拍快照时网络异常";
    } finally {
      snapLoading = false;
    }
  }

  function fmtTime(iso) {
    return iso ? new Date(iso).toLocaleString() : "—";
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 1180px; margin: 0 auto; padding: 1.5rem; }
  header.topbar {
    display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;
    border-bottom: 1px solid #44403c; padding-bottom: 0.75rem; margin-bottom: 1rem;
  }
  h1 { color: #fbbf24; margin: 0; font-size: 1.4rem; }
  h2 { margin: 0 0 0.75rem; font-size: 1.05rem; color: #fcd34d; }
  nav { display: flex; gap: 0.5rem; }
  .who { margin-left: auto; color: #a8a29e; font-size: 0.9rem; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
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
  button:disabled { opacity: 0.55; cursor: not-allowed; }
  button.secondary { background: #57534e; }
  button.nav {
    background: transparent; color: #d6d3d1; border: 1px solid #57534e;
  }
  button.nav.active { background: #d97706; border-color: #d97706; color: #fff; }
  .err { color: #fb7185; }
  .muted { color: #a8a29e; font-size: 0.9rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }

  /* 通车快照专页：三栏 */
  .snap-grid {
    display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 1rem; align-items: start;
  }
  .snap-grid section { margin-bottom: 0; }
  ul.snap-list { list-style: none; margin: 0; padding: 0; }
  ul.snap-list li { margin-bottom: 0.5rem; }
  button.snap-item {
    display: block; width: 100%; text-align: left; background: #0c0a09;
    border: 1px solid #44403c; color: #f5f5f4; padding: 0.55rem 0.7rem;
    border-radius: 6px; font-weight: 400;
  }
  button.snap-item.selected { border-color: #d97706; background: #292524; }
  button.snap-item .meta { display: block; color: #a8a29e; font-size: 0.8rem; margin-top: 0.2rem; }
  @media (max-width: 900px) {
    .snap-grid { grid-template-columns: 1fr; }
  }
</style>

<main>
  <header class="topbar">
    <h1>隧道收敛测缝台</h1>
    {#if session}
      <nav>
        <button class="nav" class:active={view === "desk"} on:click={showDesk}>收敛台账</button>
        <button class="nav" class:active={view === "snap"} on:click={showSnap}>通车快照</button>
      </nav>
      <span class="who">{session.username}（{isWriter ? "可提交" : "只读"}）</span>
      <button class="secondary" on:click={logout}>退出</button>
    {/if}
  </header>

  {#if !session}
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。登录框已预填可写账号 surveyor / surv123456；只读账号 inspector / insp123456 可查阅通车快照。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else if view === "desk"}
    <section>
      <button class="secondary" disabled={loading} on:click={refresh}>刷新列表</button>
    </section>
    {#if isWriter}
      <section>
        <label>里程桩号</label>
        <input placeholder="例如 K20+050" bind:value={chainage} />
        <label>收敛（毫米，可正可负）</label>
        <input type="number" step="0.1" bind:value={deltaMm} />
        <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
        {#if error}<p class="err">{error}</p>{/if}
      </section>
    {/if}
    <section>
      <table>
        <thead>
          <tr><th>编号</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th></tr>
        </thead>
        <tbody>
          {#each logs as row}
            <tr>
              <td>{row.id}</td>
              <td>{row.chainage}</td>
              <td>{row.delta_mm}</td>
              <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
              <td>
                {#if row.verdict}
                  <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                {:else}—{/if}
              </td>
              <td>{row.reason ?? "—"}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {:else}
    <p class="sub">通车窗打开时，把当时还在路上的测缝单抄进快照库定格留存。快照一旦落成不再随在线单据办结或改状态而变化，与左侧实时台账是新旧两套。</p>
    <div class="snap-grid">
      <section>
        <h2>新开快照</h2>
        {#if isWriter}
          <label>窗口名称</label>
          <input placeholder="例如 2026-10-05 夜间通车窗" bind:value={windowName} />
          <button disabled={snapLoading} on:click={takeSnapshot}>拍快照（抄录当前在途测缝单）</button>
        {:else}
          <p class="muted">巡检身份仅可查阅历史快照，不能拍快照。</p>
        {/if}
        {#if snapError}<p class="err">{snapError}</p>{/if}
      </section>
      <section>
        <h2>历史快照</h2>
        {#if snapshots.length === 0}
          <p class="muted">还没有快照。</p>
        {:else}
          <ul class="snap-list">
            {#each snapshots as s}
              <li>
                <button class="snap-item" class:selected={currentSnap?.id === s.id} on:click={() => openSnapshot(s.id)}>
                  {s.window_name}
                  <span class="meta">#{s.id} · {s.created_by} · {s.item_count} 条 · {fmtTime(s.created_at)}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
      <section>
        <h2>快照明细</h2>
        {#if currentSnap}
          <p class="muted">
            {currentSnap.window_name} · {currentSnap.created_by} 拍于 {fmtTime(currentSnap.created_at)}，
            当时在路上 {currentSnap.items.length} 笔，已定格。
          </p>
          <table>
            <thead>
              <tr><th>编号</th><th>断面</th><th>毫米</th></tr>
            </thead>
            <tbody>
              {#each currentSnap.items as it}
                <tr>
                  <td>{it.log_id}</td>
                  <td>{it.chainage}</td>
                  <td>{it.delta_mm}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="muted">从中间一栏选一份历史快照查看明细。</p>
        {/if}
      </section>
    </div>
  {/if}
</main>
