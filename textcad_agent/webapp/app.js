const state = {
  tasks: [],
  runs: [],
  selectedRunId: "",
  activeTaskId: "",
  pollingHandle: null,
  openDetails: new Set(),
  viewerDisposers: [],
  viewerModules: null,
  runsVisibleCount: 40,
  runtimePolicy: null,
  backendHealth: null,
};

const els = {
  taskForm: document.querySelector("#task-form"),
  promptInput: document.querySelector("#prompt-input"),
  maxIterationsInput: document.querySelector("#max-iterations-input"),
  maxNoImprovementInput: document.querySelector("#max-no-improvement-input"),
  minImprovementDeltaInput: document.querySelector("#min-improvement-delta-input"),
  runtimePolicyHint: document.querySelector("#runtime-policy-hint"),
  backendHealthSummary: document.querySelector("#backend-health-summary"),
  submitBtn: document.querySelector("#task-form button[type='submit']"),
  taskSubmitStatus: document.querySelector("#task-submit-status"),
  taskList: document.querySelector("#task-list"),
  runList: document.querySelector("#run-list"),
  runDetail: document.querySelector("#run-detail"),
  detailSubtitle: document.querySelector("#detail-subtitle"),
  activeTaskBanner: document.querySelector("#active-task-banner"),
  refreshTasksBtn: document.querySelector("#refresh-tasks-btn"),
  refreshRunsBtn: document.querySelector("#refresh-runs-btn"),
  expandAllBtn: document.querySelector("#expand-all-btn"),
  collapseAllBtn: document.querySelector("#collapse-all-btn"),
};

function setStatusMessage(message, tone = "") {
  els.taskSubmitStatus.textContent = message;
  els.taskSubmitStatus.dataset.tone = tone;
}

function upsertTask(task) {
  if (!task?.task_id) return;
  const existingIndex = state.tasks.findIndex((item) => item.task_id === task.task_id);
  if (existingIndex >= 0) {
    state.tasks.splice(existingIndex, 1, task);
  } else {
    state.tasks.unshift(task);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatJson(value) {
  return escapeHtml(JSON.stringify(value || {}, null, 2));
}

function formatValue(value, fallback = "暂无") {
  if (value === true) return "通过";
  if (value === false) return "未通过";
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatScore(value) {
  if (value === null || value === undefined || value === "") return "暂无";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return numeric.toFixed(3);
}

function stopReasonLabel(reason) {
  const labels = {
    accepted: "审查通过",
    no_quality_improvement: "连续无质量提升，提前停止并返回历史最佳",
    max_iterations_returned_best: "达到最大迭代数，返回历史最佳",
    compile_retry_limit_returned_best: "编译重试达到上限，返回历史最佳",
    design_failed_returned_best: "设计修复失败，返回历史最佳",
  };
  return labels[reason] || reason || "运行中";
}

function runtimePolicyText(policy) {
  if (!policy) return "运行策略未加载";
  const earlyStop =
    Number(policy.max_no_improvement) > 0
      ? `连续 ${policy.max_no_improvement} 轮无提升早停`
      : "早停关闭";
  return `最大 ${policy.max_iterations} 轮；${earlyStop}；最小提升 ${policy.min_improvement_delta}`;
}

function renderBackendHealthSummary(health) {
  if (!els.backendHealthSummary) return;
  if (!health) {
    els.backendHealthSummary.textContent = "后端状态未加载";
    return;
  }
  const models = health.model_policy || {};
  const design = models.design || {};
  const visual = models.visual || {};
  const runsText = health.runs_root_exists ? `${health.run_count ?? 0} 个 run` : "runs 目录不可读";
  els.backendHealthSummary.innerHTML = `
    <span class="health-dot ${health.status === "ok" ? "ok" : "bad"}"></span>
    <span>后端 ${escapeHtml(health.status || "unknown")}</span>
    <span class="text-separator">/</span>
    <span>Design ${escapeHtml(design.model || "未配置")} · ${escapeHtml(design.timeout_s ?? "?")}s</span>
    <span class="text-separator">/</span>
    <span>Visual ${escapeHtml(visual.model || "未配置")} · ${escapeHtml(visual.timeout_s ?? "?")}s</span>
    <span class="text-separator">/</span>
    <span>${escapeHtml(runsText)}</span>
  `;
}

function renderPlainList(items, fallback = "暂无") {
  const values = (items || []).filter((item) => item !== null && item !== undefined && String(item).trim());
  if (!values.length) {
    return `<div class="empty-state compact">${escapeHtml(fallback)}</div>`;
  }
  return `
    <ul class="plain-list">
      ${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ul>
  `;
}

function formatDefectItem(defect) {
  if (!defect || typeof defect !== "object") {
    return defect;
  }
  const parts = [
    defect.component ? `组件：${defect.component}` : "",
    defect.issue ? `问题：${defect.issue}` : "",
    defect.severity !== undefined ? `严重度：${defect.severity}` : "",
    defect.repair_action ? `动作：${defect.repair_action}` : "",
    defect.target_parameter ? `参数：${defect.target_parameter}` : "",
    defect.suggested_change ? `建议：${defect.suggested_change}` : "",
  ].filter(Boolean);
  return parts.join("；") || JSON.stringify(defect);
}

function renderDefectList(defects, fallback = "暂无结构化缺陷") {
  return renderPlainList((defects || []).map(formatDefectItem), fallback);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload?.error) {
        message = payload.error;
      }
    } catch (_error) {
      // ignore
    }
    throw new Error(message);
  }
  return response.json();
}

function statusBadge(status) {
  const normalized = status || "unknown";
  let className = "badge";
  if (["success", "artifact_ready"].includes(normalized)) className += " success";
  if (["running", "partial", "queued", "awaiting_user", "empty"].includes(normalized)) className += " warning";
  if (["failed"].includes(normalized)) className += " danger";
  return `<span class="${className}">${escapeHtml(normalized)}</span>`;
}

function passBadge(label, value) {
  if (value === true) return `<span class="badge success">${escapeHtml(label)}通过</span>`;
  if (value === false) return `<span class="badge danger">${escapeHtml(label)}未过</span>`;
  return `<span class="badge">${escapeHtml(label)}待定</span>`;
}

function renderProgress(task) {
  const percent = Math.max(6, Math.min(100, Math.round((task.progress_ratio || 0) * 100)));
  const maxIterations = task.max_iterations || task.runtime_policy?.max_iterations;
  return `
    <div class="progress-track">
      <div class="progress-fill" style="width:${percent}%"></div>
    </div>
    <div class="badge-row">
      <span class="badge">${escapeHtml(task.current_stage_label || task.current_stage)}</span>
      <span class="badge">${escapeHtml(task.pipeline_phase_label || task.pipeline_phase || "流程")}</span>
      <span class="badge">第 ${escapeHtml(task.iteration)}${maxIterations ? ` / ${escapeHtml(maxIterations)}` : ""} 轮</span>
      ${
        task.run_id
          ? `<span class="badge ${task.run_ready ? "success" : "warning"}">${task.run_ready ? "Run 已落盘" : "等待产物"}</span>`
          : ""
      }
      ${
        task.compile_retry_count
          ? `<span class="badge warning">编译重试 ${escapeHtml(task.compile_retry_count)}</span>`
          : ""
      }
      ${
        task.token_usage?.total_tokens
          ? `<span class="badge">tokens ${escapeHtml(task.token_usage.total_tokens)}</span>`
          : ""
      }
    </div>
  `;
}

function detailsKey(runId, iteration, section) {
  return `${runId}:${iteration}:${section}`;
}

function isDetailOpen(key, fallback = false) {
  return state.openDetails.has(key) || (!state.openDetails.size && fallback);
}

function renderActiveTaskBanner() {
  const task =
    state.tasks.find((item) => item.task_id === state.activeTaskId) ||
    state.tasks.find((item) => item.status === "running");
  if (!task) {
    els.activeTaskBanner.innerHTML = `<div class="empty-state compact">还没有进行中的任务</div>`;
    return;
  }

  els.activeTaskBanner.innerHTML = `
    <div class="detail-topline">
      <strong>当前任务</strong>
      ${statusBadge(task.status)}
    </div>
    <div class="muted">${escapeHtml(task.prompt)}</div>
    ${renderProgress(task)}
    <div class="muted small-text">${escapeHtml(runtimePolicyText(task.runtime_policy))}</div>
    ${
      task.result_summary?.compile_error
        ? `<div class="notice danger">${escapeHtml(task.result_summary.compile_error)}</div>`
        : ""
    }
  `;
}

function renderTaskList() {
  if (!state.tasks.length) {
    els.taskList.innerHTML = `<div class="empty-state compact">当前没有任务。发起一个新需求开始体验。</div>`;
    return;
  }

  els.taskList.innerHTML = state.tasks
    .map(
      (task) => `
        <button type="button" class="task-card ${task.task_id === state.activeTaskId ? "active" : ""}" data-task-id="${escapeHtml(task.task_id)}">
          <div class="card-topline">
            <span class="mono">${escapeHtml(task.task_id)}</span>
            ${statusBadge(task.status)}
          </div>
          <div>${escapeHtml(task.prompt)}</div>
          ${renderProgress(task)}
          <div class="muted small-text">${escapeHtml(runtimePolicyText(task.runtime_policy))}</div>
          ${
            task.result_summary?.latest_revision_brief
              ? `<div class="muted clamp">${escapeHtml(task.result_summary.latest_revision_brief)}</div>`
              : ""
          }
        </button>
      `,
    )
    .join("");
}

function renderRunList() {
  if (!state.runs.length) {
    els.runList.innerHTML = `<div class="empty-state compact">还没有扫描到 runs 目录内容。</div>`;
    return;
  }

  const visibleRuns = state.runs.slice(0, state.runsVisibleCount);
  const hasMore = visibleRuns.length < state.runs.length;
  els.runList.innerHTML = visibleRuns
    .map(
      (run) => `
        <button type="button" class="run-card ${run.run_id === state.selectedRunId ? "active" : ""}" data-run-id="${escapeHtml(run.run_id)}">
          <div class="card-topline">
            <span class="mono">${escapeHtml(run.run_id)}</span>
            ${statusBadge(run.status)}
          </div>
          <div><strong>${escapeHtml(run.request_summary || "未记录 request_summary")}</strong></div>
          <div class="muted">${escapeHtml(run.design_brief || run.object_type || "")}</div>
          <div class="badge-row">
            <span class="badge">迭代 ${escapeHtml(run.iteration_count)}</span>
            ${run.latest_iteration ? `<span class="badge">最新 ${escapeHtml(run.latest_iteration)}</span>` : ""}
          </div>
        </button>
      `,
    )
    .join("");

  if (hasMore) {
    els.runList.insertAdjacentHTML(
      "beforeend",
      `
        <button type="button" class="ghost load-more" data-load-more-runs>
          显示更多历史 Run（${escapeHtml(visibleRuns.length)} / ${escapeHtml(state.runs.length)}）
        </button>
      `,
    );
  }
}

function renderSection(title, contentHtml, options = {}) {
  const { open = false, key = "", className = "" } = options;
  return `
    <details class="accordion-section ${className}" ${open ? "open" : ""} ${key ? `data-detail-key="${escapeHtml(key)}"` : ""}>
      <summary>${escapeHtml(title)}</summary>
      <div class="accordion-content">
        ${contentHtml}
      </div>
    </details>
  `;
}

function renderTaskDiagnostics(task) {
  if (!task) return "";
  const summary = task.result_summary || {};
  const clarification = task.clarification_request || {};
  const missingFields = clarification.missing_fields || [];
  const logs = task.tool_logs || {};
  const policy = task.runtime_policy || {};
  return `
    <section class="run-header task-diagnostics">
      <div class="detail-topline">
        <h3>后端运行摘要</h3>
        ${statusBadge(task.status)}
      </div>
      <div class="diagnostic-grid">
        <div class="meta-item">
          <strong>流程阶段</strong>
          <span>${escapeHtml(task.pipeline_phase_label || summary.phase_label || "未知")}</span>
        </div>
        <div class="meta-item">
          <strong>当前节点</strong>
          <span>${escapeHtml(task.current_stage_label || task.current_stage || "未知")}</span>
        </div>
        <div class="meta-item">
          <strong>编译节点</strong>
          <span>${escapeHtml(summary.compile_stage || task.compile_status?.stage || "暂无")}</span>
        </div>
        <div class="meta-item">
          <strong>设计状态</strong>
          <span>${escapeHtml(summary.design_state || task.design_status?.state || "暂无")}</span>
        </div>
        <div class="meta-item">
          <strong>力学审查</strong>
          <span>${escapeHtml(formatValue(summary.physics_pass))}</span>
        </div>
        <div class="meta-item">
          <strong>视觉审查</strong>
          <span>${escapeHtml(formatValue(summary.visual_pass))}</span>
        </div>
        <div class="meta-item">
          <strong>迭代策略</strong>
          <span>${escapeHtml(runtimePolicyText(policy))}</span>
        </div>
        <div class="meta-item">
          <strong>停止原因</strong>
          <span>${escapeHtml(stopReasonLabel(summary.stop_reason))}</span>
        </div>
        <div class="meta-item">
          <strong>历史最佳</strong>
          <span>第 ${escapeHtml(summary.best_iteration ?? "暂无")} 轮 / ${escapeHtml(formatScore(summary.best_score))}</span>
        </div>
        <div class="meta-item">
          <strong>最终分数</strong>
          <span>${escapeHtml(formatScore(summary.final_score))}</span>
        </div>
      </div>
      ${
        task.run_id && !task.run_ready
          ? `<div class="notice warning">后端已创建 run_id=${escapeHtml(task.run_id)}，正在等待工作区产物写入 runs 目录。</div>`
          : ""
      }
      ${
        missingFields.length
          ? `<div class="notice warning">需要补充高风险参数：${escapeHtml(missingFields.join("、"))}</div>`
          : ""
      }
      ${
        summary.compile_error || summary.design_error || task.error
          ? `<div class="notice danger">${escapeHtml(summary.compile_error || summary.design_error || task.error)}</div>`
          : ""
      }
      ${
        task.feedback_history?.length
          ? `<section class="subsection"><h4>反馈历史</h4>${renderPlainList(task.feedback_history)}</section>`
          : ""
      }
      ${
        Object.keys(logs).length
          ? renderSection(
              "工具日志",
              `<pre class="code-block tall">${formatJson(logs)}</pre>`,
              { open: task.status === "failed" || task.final_status === "failed" },
            )
          : ""
      }
    </section>
  `;
}

function renderTaskOnlyDetail(task) {
  destroyViewers();
  if (!task) {
    renderDetail(null);
    return;
  }
  els.detailSubtitle.textContent = `${task.task_id} · ${task.pipeline_phase_label || task.current_stage_label || "运行中"}`;
  els.runDetail.innerHTML = `
    ${renderTaskDiagnostics(task)}
    <section class="empty-state">
      <p>${task.run_id ? "Run 目录尚未可读，结果产物出现后会自动切换到详情。" : "后端任务已创建，正在等待第一批进度事件。"}</p>
      <p>当前节点：${escapeHtml(task.current_stage_label || task.current_stage || "未知")}</p>
    </section>
  `;
  bindDetailsState();
}

function renderViewer(iteration) {
  if (!iteration.artifacts?.stl) {
    return `
      <div class="viewer-panel">
        <div class="viewer-head">
          <h4>浏览器内 3D 预览</h4>
          <span class="badge warning">当前轮没有 STL</span>
        </div>
        <div class="viewer-empty">这一轮还没有产出 STL，暂时无法加载 3D 模型。</div>
      </div>
    `;
  }

  return `
    <div class="viewer-panel">
      <div class="viewer-head">
        <h4>浏览器内 3D 预览</h4>
        <div class="inline-list">
          <span class="badge">拖拽旋转</span>
          <span class="badge">滚轮缩放</span>
        </div>
      </div>
      <canvas
        class="viewer-canvas"
        data-stl-url="${escapeHtml(iteration.artifacts.stl)}"
        data-viewer-id="${escapeHtml(`viewer-${iteration.iteration}`)}"
      ></canvas>
    </div>
  `;
}

function renderRenderGallery(iteration) {
  if (!iteration.render_images?.length) {
    return `<div class="empty-state compact">这一轮没有可用截图。</div>`;
  }

  return `
    <div class="gallery">
      ${iteration.render_images
        .map(
          (image) => `
            <a target="_blank" rel="noreferrer" href="${image.url}">
              <img src="${image.url}" alt="${escapeHtml(image.name)}" loading="lazy" />
            </a>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderIterationCard(runId, iteration, isLatest) {
  const rootKey = detailsKey(runId, iteration.iteration, "root");
  const reviewKey = detailsKey(runId, iteration.iteration, "review");
  const loopKey = detailsKey(runId, iteration.iteration, "loop");
  const codeKey = detailsKey(runId, iteration.iteration, "code");
  const dataKey = detailsKey(runId, iteration.iteration, "data");

  const summaryBadges = `
    <div class="iteration-summary-meta">
      ${iteration.physics_review?.pass === true ? '<span class="badge success">力学通过</span>' : ""}
      ${iteration.physics_review?.pass === false ? '<span class="badge danger">力学未过</span>' : ""}
      ${iteration.visual_review?.pass === true ? '<span class="badge success">视觉通过</span>' : ""}
      ${iteration.visual_review?.pass === false ? '<span class="badge danger">视觉未过</span>' : ""}
      ${iteration.artifacts?.stl ? '<span class="badge">已产出 STL</span>' : '<span class="badge warning">无 STL</span>'}
      ${
        iteration.render_images?.length
          ? `<span class="badge">${escapeHtml(iteration.render_images.length)} 张截图</span>`
          : ""
      }
    </div>
  `;

  const quickLinks = `
    <div class="link-row">
      ${iteration.artifacts?.stl ? `<a class="link-chip" target="_blank" rel="noreferrer" href="${iteration.artifacts.stl}">打开 STL</a>` : ""}
      ${iteration.artifacts?.step ? `<a class="link-chip" target="_blank" rel="noreferrer" href="${iteration.artifacts.step}">打开 STEP</a>` : ""}
      ${iteration.artifacts?.mesh ? `<a class="link-chip" target="_blank" rel="noreferrer" href="${iteration.artifacts.mesh}">打开 Mesh</a>` : ""}
      ${iteration.artifacts?.vtk ? `<a class="link-chip" target="_blank" rel="noreferrer" href="${iteration.artifacts.vtk}">打开 VTK</a>` : ""}
      ${
        iteration.artifacts?.generated_model
          ? `<a class="link-chip" target="_blank" rel="noreferrer" href="${iteration.artifacts.generated_model}">查看 CadQuery</a>`
          : ""
      }
    </div>
  `;

  const overview = `
    ${renderViewer(iteration)}
    ${quickLinks}
    <div class="split">
      <section class="subsection">
        <h4>修订摘要</h4>
        <pre class="text-block light">${escapeHtml(iteration.revision_brief || "暂无")}</pre>
      </section>
      <section class="subsection">
        <h4>力学报告</h4>
        <pre class="text-block light">${escapeHtml(iteration.physics_report || "暂无")}</pre>
      </section>
    </div>
    <section class="subsection">
      <h4>渲染截图</h4>
      ${renderRenderGallery(iteration)}
    </section>
  `;

  const reviewContent = `
    <div class="split">
      <section class="subsection">
        <h4>视觉审查 JSON</h4>
        <pre class="code-block tall">${formatJson(iteration.visual_review)}</pre>
      </section>
      <section class="subsection">
        <h4>力学审查 JSON</h4>
        <pre class="code-block tall">${formatJson(iteration.physics_review)}</pre>
      </section>
    </div>
  `;

  const loopContent = `
    <div class="split">
      <section class="subsection">
        <h4>工程基线 Prompt</h4>
        <pre class="text-block light tall">${escapeHtml(iteration.engineering_prompt || "暂无")}</pre>
      </section>
      <section class="subsection">
        <h4>本轮修复输入</h4>
        <pre class="text-block light tall">${escapeHtml(iteration.revision_brief || "首轮生成或本轮无需修复。")}</pre>
      </section>
    </div>
    <div class="split">
      <section class="subsection">
        <h4>视觉问题</h4>
        ${renderPlainList(
          [
            ...(iteration.visual_review?.issues || []),
            ...(iteration.visual_review?.missing_requirements || []),
            ...(iteration.visual_review?.recommended_edits || []),
          ],
          "视觉审查暂无自然语言问题",
        )}
        ${renderDefectList(iteration.visual_review?.defects, "视觉审查暂无结构化缺陷")}
      </section>
      <section class="subsection">
        <h4>力学反馈</h4>
        ${renderPlainList([
          ...(iteration.physics_review?.violations || []),
          ...(iteration.physics_review?.recommended_edits || []),
          iteration.physics_report,
        ], "力学审查暂无问题")}
      </section>
    </div>
  `;

  const codeContent = `
    <div class="split">
      <section class="subsection">
        <h4>生成代码</h4>
        <pre class="code-block tall">${escapeHtml(iteration.generated_model_code || "# 暂无代码")}</pre>
      </section>
      <section class="subsection">
        <h4>设计请求 / Prompt</h4>
        <pre class="code-block tall">${escapeHtml(iteration.design_request || "暂无")}</pre>
      </section>
    </div>
  `;

  const dataContent = `
    <div class="split three-up">
      <section class="subsection">
        <h4>Clarified Spec</h4>
        <pre class="code-block tall">${formatJson(iteration.clarified_spec)}</pre>
      </section>
      <section class="subsection">
        <h4>Analysis Config</h4>
        <pre class="code-block tall">${formatJson(iteration.analysis_config)}</pre>
      </section>
      <section class="subsection">
        <h4>Scale / Render Meta</h4>
        <pre class="code-block tall">${formatJson(iteration.scale_metadata)}</pre>
      </section>
    </div>
  `;

  return `
    <details class="iteration-card" data-detail-key="${escapeHtml(rootKey)}" ${isDetailOpen(rootKey, isLatest) ? "open" : ""}>
      <summary class="iteration-summary">
        <div class="iteration-summary-row">
          <div class="iteration-summary-title">
            <h3>第 ${escapeHtml(iteration.iteration)} 轮</h3>
            ${summaryBadges}
          </div>
          <div class="iteration-chevron">⌄</div>
        </div>
      </summary>
      <div class="iteration-body">
        ${overview}
        ${renderSection("反馈闭环", loopContent, { open: isDetailOpen(loopKey, false), key: loopKey })}
        ${renderSection("审查结果", reviewContent, { open: isDetailOpen(reviewKey, false), key: reviewKey })}
        ${renderSection("代码与请求", codeContent, { open: isDetailOpen(codeKey, false), key: codeKey })}
        ${renderSection("结构化数据", dataContent, { open: isDetailOpen(dataKey, false), key: dataKey })}
      </div>
    </details>
  `;
}

function destroyViewers() {
  state.viewerDisposers.forEach((dispose) => dispose());
  state.viewerDisposers = [];
}

async function loadViewerModules() {
  if (!state.viewerModules) {
    state.viewerModules = Promise.all([
      import("/static/vendor/three.module.js"),
      import("/static/vendor/OrbitControls.js"),
      import("/static/vendor/STLLoader.js"),
    ]).then(([THREE, controlsModule, loaderModule]) => ({
      THREE,
      OrbitControls: controlsModule.OrbitControls,
      STLLoader: loaderModule.STLLoader,
    })).catch((error) => {
      state.viewerModules = null;
      throw error;
    });
  }
  return state.viewerModules;
}

function fitCameraToObject(THREE, camera, controls, object) {
  const box = new THREE.Box3().setFromObject(object);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const fov = camera.fov * (Math.PI / 180);
  let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
  cameraZ *= 1.8;
  camera.position.set(center.x + cameraZ * 0.85, center.y + cameraZ * 0.65, center.z + cameraZ * 0.9);
  camera.near = Math.max(0.1, maxDim / 100);
  camera.far = Math.max(1000, maxDim * 20);
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

async function initStlViewer(canvas) {
  const stlUrl = canvas.dataset.stlUrl;
  if (!stlUrl) return;

  const { THREE, OrbitControls, STLLoader } = await loadViewerModules();
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, canvas.clientWidth / canvas.clientHeight, 0.1, 5000);

  const ambient = new THREE.HemisphereLight(0xf2fcff, 0x2e3538, 1.4);
  scene.add(ambient);

  const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
  keyLight.position.set(4, 8, 10);
  scene.add(keyLight);

  const rimLight = new THREE.DirectionalLight(0xb0f1ff, 1.2);
  rimLight.position.set(-7, 2, -6);
  scene.add(rimLight);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = false;

  const loader = new STLLoader();
  const response = await fetch(stlUrl);
  if (!response.ok) {
    throw new Error(`加载 STL 失败: ${response.status}`);
  }
  const arrayBuffer = await response.arrayBuffer();
  const geometry = loader.parse(arrayBuffer);
  geometry.computeVertexNormals();
  geometry.center();

  const material = new THREE.MeshStandardMaterial({
    color: 0xd9e4e8,
    metalness: 0.08,
    roughness: 0.54,
  });

  const mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  const edgeGeometry = new THREE.EdgesGeometry(geometry);
  const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x2a4c57, transparent: true, opacity: 0.45 });
  const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
  scene.add(edges);

  fitCameraToObject(THREE, camera, controls, mesh);

  let disposed = false;
  let frameId = 0;

  const render = () => {
    if (disposed) return;
    controls.update();
    renderer.render(scene, camera);
    frameId = requestAnimationFrame(render);
  };
  render();

  const resize = () => {
    if (disposed) return;
    const width = canvas.clientWidth || 1;
    const height = canvas.clientHeight || 1;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvas);
  window.addEventListener("resize", resize);

  state.viewerDisposers.push(() => {
    disposed = true;
    cancelAnimationFrame(frameId);
    resizeObserver.disconnect();
    window.removeEventListener("resize", resize);
    controls.dispose();
    geometry.dispose();
    edgeGeometry.dispose();
    material.dispose();
    edgeMaterial.dispose();
    renderer.dispose();
  });
}

async function initViewers() {
  destroyViewers();
  const canvases = Array.from(document.querySelectorAll(".viewer-canvas"));
  await Promise.all(
    canvases.map(async (canvas) => {
      try {
        await initStlViewer(canvas);
      } catch (error) {
        const parent = canvas.parentElement;
        if (parent) {
          canvas.replaceWith(
            Object.assign(document.createElement("div"), {
              className: "viewer-empty",
              textContent: error.message || "3D 预览加载失败。",
            }),
          );
        }
      }
    }),
  );
}

function renderRunDiagnostics(run, task) {
  const latest = run?.iterations?.[run.iterations.length - 1] || {};
  const taskSummary = task?.result_summary || {};
  const policy = task?.runtime_policy || state.runtimePolicy;
  return `
    <section class="run-header">
      <div class="detail-topline">
        <h3>后端运行摘要</h3>
        ${statusBadge(task?.status || run?.status)}
      </div>
      <div class="diagnostic-grid">
        <div class="meta-item">
          <strong>流程阶段</strong>
          <span>${escapeHtml(task?.pipeline_phase_label || taskSummary.phase_label || "历史 Run")}</span>
        </div>
        <div class="meta-item">
          <strong>当前/最终节点</strong>
          <span>${escapeHtml(task?.current_stage_label || (run?.latest_iteration ? `第 ${run.latest_iteration} 轮` : "未知"))}</span>
        </div>
        <div class="meta-item">
          <strong>编译状态</strong>
          <span>${escapeHtml(formatValue(taskSummary.compile_success, latest.artifacts?.stl ? "已产出 STL" : "暂无"))}</span>
        </div>
        <div class="meta-item">
          <strong>设计模型状态</strong>
          <span>${escapeHtml(taskSummary.design_state || "暂无")}</span>
        </div>
        <div class="meta-item">
          <strong>FEA 结论</strong>
          <span>${escapeHtml(formatValue(taskSummary.physics_pass ?? latest.physics_review?.pass))}</span>
        </div>
        <div class="meta-item">
          <strong>VLM 结论</strong>
          <span>${escapeHtml(formatValue(taskSummary.visual_pass ?? latest.visual_review?.pass))}</span>
        </div>
        <div class="meta-item">
          <strong>迭代策略</strong>
          <span>${escapeHtml(task ? runtimePolicyText(policy) : "历史 Run 未记录上限")}</span>
        </div>
        <div class="meta-item">
          <strong>停止原因</strong>
          <span>${escapeHtml(stopReasonLabel(taskSummary.stop_reason))}</span>
        </div>
        <div class="meta-item">
          <strong>历史最佳</strong>
          <span>第 ${escapeHtml(taskSummary.best_iteration ?? "暂无")} 轮 / ${escapeHtml(formatScore(taskSummary.best_score))}</span>
        </div>
        <div class="meta-item">
          <strong>最终分数</strong>
          <span>${escapeHtml(formatScore(taskSummary.final_score))}</span>
        </div>
      </div>
      ${
        taskSummary.max_disp_mm !== null && taskSummary.max_disp_mm !== undefined
          ? `<div class="notice">最大位移：${escapeHtml(taskSummary.max_disp_mm)} mm</div>`
          : ""
      }
      ${
        taskSummary.compile_error || taskSummary.design_error || task?.error
          ? `<div class="notice danger">${escapeHtml(taskSummary.compile_error || taskSummary.design_error || task.error)}</div>`
          : ""
      }
    </section>
  `;
}

function renderDetail(run, task = null) {
  destroyViewers();

  if (!run) {
    els.runDetail.innerHTML = `
      <div class="empty-state">
        <p>还没有选中的 run。</p>
        <p>创建新任务后会自动切换到该 run；也可以直接点开左侧历史记录。</p>
      </div>
    `;
    return;
  }

  els.detailSubtitle.textContent = `${run.run_id} · 共 ${run.iteration_count} 轮`;
  els.runDetail.innerHTML = `
    <section class="run-header">
      <div class="detail-topline">
        <h3>${escapeHtml(run.request_summary || "未记录需求摘要")}</h3>
        ${statusBadge(run.status)}
      </div>
      <div class="muted">${escapeHtml(run.design_brief || "无设计摘要")}</div>
      <div class="run-meta">
        <div class="meta-item">
          <strong>Run ID</strong>
          <span class="mono">${escapeHtml(run.run_id)}</span>
        </div>
        <div class="meta-item">
          <strong>对象类型</strong>
          <span>${escapeHtml(run.object_type || "未知")}</span>
        </div>
        <div class="meta-item">
          <strong>最新更新时间</strong>
          <span>${escapeHtml(run.updated_at || "未知")}</span>
        </div>
        <div class="meta-item">
          <strong>迭代轮数</strong>
          <span>${escapeHtml(run.iteration_count)}</span>
        </div>
      </div>
    </section>
    ${renderRunDiagnostics(run, task)}
    <section class="iteration-grid">
      ${run.iterations.map((iteration, index) => renderIterationCard(run.run_id, iteration, index === run.iterations.length - 1)).join("")}
    </section>
  `;

  bindDetailsState();
  initViewers().catch((error) => console.error(error));
}

function bindDetailsState() {
  document.querySelectorAll("[data-detail-key]").forEach((detail) => {
    detail.addEventListener("toggle", () => {
      const key = detail.dataset.detailKey;
      if (!key) return;
      if (detail.open) {
        state.openDetails.add(key);
      } else {
        state.openDetails.delete(key);
      }
    });
  });
}

async function refreshTasks() {
  const payload = await fetchJson("/api/tasks");
  state.tasks = payload.tasks || [];
  renderTaskList();
  renderActiveTaskBanner();
}

async function refreshConfig() {
  const payload = await fetchJson("/api/config");
  state.runtimePolicy = payload.runtime_policy || null;
  if (state.runtimePolicy && els.maxIterationsInput && !els.maxIterationsInput.value) {
    els.maxIterationsInput.value = state.runtimePolicy.max_iterations;
    els.maxIterationsInput.max = state.runtimePolicy.web_max_iterations_limit || 20;
  }
  if (state.runtimePolicy && els.maxNoImprovementInput && !els.maxNoImprovementInput.value) {
    els.maxNoImprovementInput.value = state.runtimePolicy.max_no_improvement;
    els.maxNoImprovementInput.max = state.runtimePolicy.web_max_no_improvement_limit || 20;
  }
  if (state.runtimePolicy && els.minImprovementDeltaInput && !els.minImprovementDeltaInput.value) {
    els.minImprovementDeltaInput.value = state.runtimePolicy.min_improvement_delta;
  }
  if (els.runtimePolicyHint) {
    els.runtimePolicyHint.textContent = state.runtimePolicy
      ? `${runtimePolicyText(state.runtimePolicy)}；早停轮数设为 0 可关闭早停`
      : "运行策略未加载，可直接使用默认设置";
  }
}

async function refreshHealth() {
  const payload = await fetchJson("/api/health");
  state.backendHealth = payload || null;
  renderBackendHealthSummary(state.backendHealth);
}

async function refreshRuns() {
  const payload = await fetchJson("/api/runs");
  state.runs = payload.runs || [];
  renderRunList();
}

async function loadRunDetail(runId) {
  if (!runId) {
    renderDetail(null);
    return;
  }

  const relatedTask = state.tasks.find((item) => item.run_id === runId) || null;
  try {
    const run = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
    state.selectedRunId = run.run_id;
    renderRunList();
    renderDetail(run, relatedTask);
  } catch (error) {
    if (relatedTask) {
      renderTaskOnlyDetail(relatedTask);
      return;
    }
    throw error;
  }
}

async function submitTask(prompt, maxIterations, maxNoImprovement, minImprovementDelta) {
  const task = await fetchJson("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      max_iterations: maxIterations,
      max_no_improvement: maxNoImprovement,
      min_improvement_delta: minImprovementDelta,
    }),
  });
  upsertTask(task);
  state.activeTaskId = task.task_id;
  state.selectedRunId = "";
  setStatusMessage(`任务已启动，最多运行 ${task.max_iterations || maxIterations} 轮。`, "success");
  renderTaskList();
  renderActiveTaskBanner();
  renderTaskOnlyDetail(task);
  try {
    await refreshTasks();
  } catch (error) {
    console.error(error);
    setStatusMessage(`任务已创建，但刷新任务列表失败：${error.message}`, "warning");
  }
}

function setAllDetails(expanded) {
  document.querySelectorAll("[data-detail-key]").forEach((detail) => {
    detail.open = expanded;
    const key = detail.dataset.detailKey;
    if (!key) return;
    if (expanded) {
      state.openDetails.add(key);
    } else {
      state.openDetails.delete(key);
    }
  });
}

function bindEvents() {
  els.taskForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const prompt = els.promptInput.value.trim();
    const maxIterations = Number.parseInt(els.maxIterationsInput?.value || "", 10);
    const maxNoImprovement = Number.parseInt(els.maxNoImprovementInput?.value || "", 10);
    const minImprovementDelta = Number.parseFloat(els.minImprovementDeltaInput?.value || "");
    if (!prompt) {
      setStatusMessage("请输入需求描述。", "warning");
      return;
    }
    if (!Number.isInteger(maxIterations) || maxIterations < 1 || maxIterations > Number(els.maxIterationsInput?.max || 20)) {
      setStatusMessage(`最大迭代数必须在 1-${els.maxIterationsInput?.max || 20} 之间。`, "warning");
      return;
    }
    if (
      !Number.isInteger(maxNoImprovement) ||
      maxNoImprovement < 0 ||
      maxNoImprovement > Number(els.maxNoImprovementInput?.max || 20)
    ) {
      setStatusMessage(`早停轮数必须在 0-${els.maxNoImprovementInput?.max || 20} 之间，0 表示关闭。`, "warning");
      return;
    }
    if (Number.isNaN(minImprovementDelta) || minImprovementDelta < 0 || minImprovementDelta > 1) {
      setStatusMessage("提升阈值必须在 0-1 之间。", "warning");
      return;
    }
    const originalLabel = els.submitBtn?.textContent || "";
    if (els.submitBtn) {
      els.submitBtn.disabled = true;
      els.submitBtn.textContent = "启动中…";
    }
    setStatusMessage("正在创建任务…");
    try {
      await submitTask(prompt, maxIterations, maxNoImprovement, minImprovementDelta);
      els.promptInput.value = "";
    } catch (error) {
      setStatusMessage(`任务创建失败：${error.message}`, "danger");
    } finally {
      if (els.submitBtn) {
        els.submitBtn.disabled = false;
        els.submitBtn.textContent = originalLabel;
      }
    }
  });

  els.taskList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-task-id]");
    if (!button) return;
    const taskId = button.dataset.taskId;
    state.activeTaskId = taskId;
    const task = state.tasks.find((item) => item.task_id === taskId);
    renderTaskList();
    renderActiveTaskBanner();
    if (task?.run_id) {
      await loadRunDetail(task.run_id);
    } else {
      renderTaskOnlyDetail(task);
    }
  });

  els.runList.addEventListener("click", async (event) => {
    const loadMoreButton = event.target.closest("[data-load-more-runs]");
    if (loadMoreButton) {
      state.runsVisibleCount += 40;
      renderRunList();
      return;
    }
    const button = event.target.closest("[data-run-id]");
    if (!button) return;
    await loadRunDetail(button.dataset.runId);
  });

  els.refreshTasksBtn.addEventListener("click", () => refreshTasks().catch(console.error));
  els.refreshRunsBtn.addEventListener("click", () => refreshRuns().catch(console.error));
  els.expandAllBtn.addEventListener("click", () => setAllDetails(true));
  els.collapseAllBtn.addEventListener("click", () => setAllDetails(false));
}

function ensurePolling() {
  if (state.pollingHandle) {
    clearInterval(state.pollingHandle);
  }
  state.pollingHandle = setInterval(async () => {
    try {
      await refreshTasks();
      const activeTask = state.tasks.find((item) => item.task_id === state.activeTaskId);
      if (activeTask?.run_id) {
        await loadRunDetail(activeTask.run_id);
      } else if (activeTask) {
        renderTaskOnlyDetail(activeTask);
      } else if (state.selectedRunId) {
        await loadRunDetail(state.selectedRunId);
      }
      await refreshRuns();
    } catch (error) {
      console.error(error);
    }
  }, 1500);
}

async function bootstrap() {
  bindEvents();
  const bootErrors = [];
  try {
    await refreshHealth();
  } catch (error) {
    bootErrors.push(`后端状态：${error.message}`);
    renderBackendHealthSummary(null);
  }
  try {
    await refreshConfig();
  } catch (error) {
    bootErrors.push(`运行策略：${error.message}`);
  }
  try {
    await refreshTasks();
  } catch (error) {
    bootErrors.push(`任务列表：${error.message}`);
  }
  try {
    await refreshRuns();
  } catch (error) {
    bootErrors.push(`Run 列表：${error.message}`);
  }
  const firstRun = state.runs[0];
  if (firstRun?.run_id) {
    try {
      await loadRunDetail(firstRun.run_id);
    } catch (error) {
      bootErrors.push(`Run 详情：${error.message}`);
    }
  }
  ensurePolling();
  if (bootErrors.length) {
    setStatusMessage(`页面已启动，但部分数据加载失败：${bootErrors.join("；")}`, "warning");
  }
}

bootstrap().catch((error) => {
  setStatusMessage(`页面初始化失败：${error.message}`, "danger");
  els.runDetail.innerHTML = `<div class="empty-state">页面初始化失败：${escapeHtml(error.message)}</div>`;
});
