// Project onboarding uses the existing selector and terminal project identity.
(() => {
  let preview = null;
  let generation = 0;
  let debounce;
  let jobId = sessionStorage.getItem('devPanelCloneJob');
  let busy = Boolean(jobId);
  let polling = false;

  function controls() {
    $('repositoryUrl').disabled = busy;
    $('cloneProject').textContent = preview?.exists ? 'Replace local copy with GitHub version' : 'Clone Project';
    $('cloneProject').disabled = busy || !preview || (preview.exists && !preview.canReplace);
    $('cancelClone').classList.toggle('hidden', !busy || !jobId);
    $('openExistingProject').classList.toggle('hidden', busy || !preview?.existingProject);
  }

  function renderPreview(data) {
    preview = data;
    $('projectClonePreview').classList.toggle('hidden', !data);
    $('cloneRepository').textContent = data?.repository || '';
    $('cloneLocalPath').textContent = data?.localPath || '';
    controls();
  }

  async function inspect() {
    const current = ++generation;
    renderPreview(null);
    if (!$('repositoryUrl').value.trim()) { $('cloneStatus').textContent = 'Paste an SSH or HTTPS repository URL.'; return; }
    $('cloneStatus').textContent = 'Checking repository URL…';
    try {
      const data = await api('/api/projects/preview', {method:'POST', body:{url:$('repositoryUrl').value.trim()}});
      if (current !== generation || busy) return;
      renderPreview(data);
      $('cloneStatus').textContent = data.exists
        ? (data.canReplace ? 'The local project already exists. You can open it or replace it with the GitHub version after confirming a backup.' : 'The local project already exists. This destination cannot be replaced; open it if available.')
        : 'Ready to clone. Git uses the server user’s existing authentication.';
    } catch (error) {
      if (current === generation && !busy) $('cloneStatus').textContent = error.message;
    }
  }

  async function selectProject(name) {
    await loadProjects();
    $('project').value = name;
    await $('project').onchange();
    if (selectedProject === name) {
      $('addProjectDialog').close();
      setView('repository');
    }
  }

  async function poll() {
    if (!jobId || polling) return;
    polling = true;
    try {
      const job = await api(`/api/projects/clone-status?id=${encodeURIComponent(jobId)}`);
      $('cloneOutput').textContent = job.output;
      $('cloneOutput').classList.toggle('hidden', !job.output);
      if (job.state === 'cloning' || job.state === 'registering') {
        $('cloneStatus').textContent = 'Cloning project… You can close this dialog and return.';
      } else {
        busy = false;
        jobId = null;
        sessionStorage.removeItem('devPanelCloneJob');
        if (job.state === 'complete') {
          $('cloneStatus').textContent = job.backup ? `Project replaced successfully. Original folder backed up at ${job.backup}` : 'Project cloned successfully.';
          renderPreview({...preview, exists:true, existingProject:job.project});
          $('openExistingProject').textContent = 'Open project';
          await loadProjects();
          if ($('addProjectDialog').open && !job.backup) await selectProject(job.project);
        } else {
          $('cloneStatus').textContent = job.error;
          // Revalidate before allowing a retry; a preserved directory stays blocked.
          try {
            renderPreview(await api('/api/projects/preview', {method:'POST', body:{url:$('repositoryUrl').value.trim()}}));
          } catch { renderPreview(null); }
        }
      }
    } catch (error) {
      $('cloneStatus').textContent = `${error.message} Reopen Add Project to check again.`;
      if (error.data) {
        busy = false; jobId = null;
        sessionStorage.removeItem('devPanelCloneJob');
        await loadProjects().catch(() => {});
      }
    } finally {
      polling = false;
      controls();
      if (jobId) setTimeout(poll, 700);
    }
  }

  $('repositoryUrl').oninput = () => {
    ++generation;
    renderPreview(null);
    clearTimeout(debounce);
    debounce = setTimeout(inspect, 250);
  };
  $('addProject').onclick = () => {
    $('addProjectDialog').showModal();
    controls();
    if (jobId) poll();
    else if (!preview) inspect();
    $('repositoryUrl').focus();
  };
  $('closeAddProject').onclick = () => $('addProjectDialog').close();
  $('openExistingProject').onclick = async () => {
    try { await selectProject(preview.existingProject); }
    catch (error) { $('cloneStatus').textContent = error.message; }
  };
  $('cloneProject').onclick = async () => {
    if (busy || !preview || (preview.exists && !preview.canReplace)) return;
    const replace = Boolean(preview.exists);
    if (replace && !confirm(`Replace local copy with GitHub version? The current folder (${preview.localPath}) will be moved to a backup inside the projects directory under .backups. Local commits and uncommitted files will remain in the backup. If cloning fails, the original folder will be restored.`)) return;
    busy = true;
    ++generation;
    controls();
    $('cloneOutput').textContent = '';
    $('cloneOutput').classList.add('hidden');
    $('cloneStatus').textContent = 'Starting clone…';
    try {
      const job = await api('/api/projects/clone', {method:'POST', body:{url:$('repositoryUrl').value.trim(), replace}});
      jobId = job.id;
      sessionStorage.setItem('devPanelCloneJob', jobId);
      controls();
      poll();
    } catch (error) {
      busy = false;
      $('cloneStatus').textContent = error.message;
      if (error.data?.exists) renderPreview(error.data);
      controls();
    }
  };
  $('cancelClone').onclick = async () => {
    try {
      await api('/api/projects/cancel', {method:'POST', body:{id:jobId}});
      $('cloneStatus').textContent = 'Cancelling clone and cleaning up…';
    } catch (error) { $('cloneStatus').textContent = error.message; }
  };
})();
