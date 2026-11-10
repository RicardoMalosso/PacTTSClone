import {api} from './api.js';
import {$} from './dom.js';

const base = '/api/tournaments';

function audio(clip, label) {
  const player = document.createElement('audio');
  player.controls = true;
  player.preload = 'none';
  player.src = '/api/jobs/' + encodeURIComponent(clip) + '/audio';
  player.setAttribute('aria-label', label);
  player.title = 'Preview ' + label + ' in this browser.';
  return player;
}

function button(label, hint, action) {
  const node = document.createElement('button');
  node.type = 'button';
  node.textContent = label;
  node.title = hint;
  node.onclick = () => run(action);
  return node;
}

async function run(action) {
  const controls = $('tournament-controls');
  if (controls.disabled) return;
  controls.disabled = true;
  $('tournament-status').textContent = '';
  try {
    await action();
  } catch (error) {
    $('tournament-status').textContent = error.message;
  } finally {
    controls.disabled = false;
  }
}

async function startPoll(endpoint, match) {
  const channel = $('tournament-poll-channel').value;
  if (!channel) throw new Error('Select a Twitch poll channel first.');
  await api(endpoint + '/poll', {method: 'POST', body: {match_id: match.id, channel}});
  $('tournament-status').textContent = 'Twitch poll posted for this matchup.';
}

function showView(view) {
  const panels = {compare: 'tournament-pair', bracket: 'tournament-bracket-view',
    ranking: 'tournament-ranking-view'};
  for (const [name, panel] of Object.entries(panels)) {
    $(panel).hidden = name !== view;
    $('tournament-show-' + name).setAttribute('aria-pressed', String(name === view));
    if (name !== view) $(panel).querySelectorAll('audio').forEach(player => player.pause());
  }
}

function renderResults(rows, bracket) {
  const labels = new Map(bracket.clips.map(({id}, index) => [id, 'Clip ' + (index + 1)]));
  const ranking = $('tournament-ranking');
  ranking.replaceChildren();
  for (const row of rows) {
    const item = document.createElement('li');
    const label = labels.get(row.clip);
    item.title = row.provisional
      ? 'Provisional until this clip has five counted comparisons.'
      : 'Placement is based on counted head-to-head choices.';
    item.append(label + ' · ' + row.comparisons + ' comparisons',
      row.provisional ? ' · Provisional' : '', audio(row.clip, label));
    ranking.append(item);
  }
  $('tournament-ranking-empty').hidden = rows.length > 0;

  const roster = $('tournament-clips');
  roster.replaceChildren();
  for (const clip of bracket.clips) {
    const item = document.createElement('li');
    const label = labels.get(clip.id);
    item.append(label);
    if (clip.tag) {
      item.title = 'Reported locally and removed from this tournament.';
      item.append(' · ' + clip.tag);
    }
    if (clip.playable) item.append(audio(clip.id, label));
    else item.append(' · MP3 unavailable');
    roster.append(item);
  }

  const graphic = $('tournament-bracket');
  graphic.replaceChildren();
  if (!bracket.matches.length) graphic.textContent = 'No matchups yet.';
  for (const match of bracket.matches) {
    const card = document.createElement('div');
    card.className = 'tournament-match';
    const sides = document.createElement('div');
    for (const side of ['a', 'b']) {
      const slot = document.createElement('div');
      slot.className = 'tournament-slot';
      slot.textContent = labels.get(match[side]);
      sides.append(slot);
    }
    const result = document.createElement('div');
    result.className = 'tournament-result';
    if (!match.counts) result.textContent = 'Out of ranking';
    else if (!match.result) result.textContent = 'Pending';
    else if (match.result === 'skip') result.textContent = 'Skipped';
    else result.textContent = labels.get(match[match.result]) + ' won';
    result.title = match.counts
      ? 'Recorded outcome of this matchup.'
      : 'This matchup is excluded because a clip was removed or is unavailable.';
    card.append(sides, result);
    graphic.append(card);
  }
  return labels;
}

async function refreshMatch() {
  const tournament = $('tournament-select').value;
  const panel = $('tournament-pair');
  panel.replaceChildren();
  $('tournament-views').hidden = !tournament;
  if (!tournament) {
    showView('compare');
    return;
  }

  const endpoint = base + '/' + tournament;
  const match = await api(endpoint + '/pair', {method: 'POST'});
  const [rows, bracket] = await Promise.all([api(endpoint + '/leaderboard'),
    api(endpoint + '/bracket')]);
  const labels = renderResults(rows, bracket);
  if (!match) {
    panel.textContent = 'No more matchups available.';
    return;
  }

  const vote = async result => {
    await api(endpoint + '/vote', {method: 'POST', body: {match_id: match.id, result}});
    await refreshMatch();
  };
  for (const side of ['a', 'b']) {
    const clip = match[side];
    const label = side.toUpperCase();
    const group = document.createElement('div');
    group.append(
      label + ' · ' + labels.get(clip),
      audio(clip, 'Clip ' + label),
      button('Pick ' + label, 'Count a local win for Clip ' + label + '.', () => vote(side)),
      button('Terrible horrible (' + label + ')',
        'Remove this clip from the tournament and tag it “shit from a butt.”', async () => {
        const report = await api(endpoint + '/report/' + encodeURIComponent(clip), {method: 'POST'});
        await refreshMatch();
        $('tournament-status').textContent = 'Clip removed · ' + report.tag;
      }),
    );
    panel.append(group);
  }
  panel.append(
    button('Skip', 'Move to the next matchup without awarding a win.', () => vote('skip')),
    button('Start Twitch poll', 'Ask viewers to pick A or B. The result is advisory.',
      () => startPoll(endpoint, match)),
  );
  if ($('tournament-auto-poll').checked && $('tournament-poll-channel').value) {
    await startPoll(endpoint, match);
  }
}

async function load(selected = $('tournament-select').value) {
  const select = $('tournament-select');
  const periods = {today: 'Today', week: 'Last week', range: 'Date range',
    winners: 'Previous Winners', all: 'All', month: 'Last month'};
  const [tournaments, channels] = await Promise.all([api(base), api('/api/channels')]);
  const pollChannel = $('tournament-poll-channel');
  const previous = pollChannel.value;
  pollChannel.replaceChildren(new Option('No Twitch polls', ''), ...channels.map(
    ({name}) => new Option('#' + name, name),
  ));
  if (channels.some(({name}) => name === previous)) pollChannel.value = previous;
  select.replaceChildren(...tournaments.map(({id, period, created_at}) =>
    new Option(periods[period] + ' · ' + new Date(created_at * 1000).toLocaleString(), id),
  ));
  if (tournaments.some(({id}) => id === selected)) select.value = selected;
  await refreshMatch();
}

export function loadTournaments() {
  return run(() => load());
}

export function initTournaments() {
  for (const view of ['compare', 'bracket', 'ranking']) {
    $('tournament-show-' + view).onclick = () => showView(view);
  }
  $('tournament-period').onchange = () => {
    $('tournament-date-range').hidden = $('tournament-period').value !== 'range';
  };
  $('tournament-select').onchange = () => run(refreshMatch);
  $('tournament-create').onclick = () => run(async () => {
    const body = {period: $('tournament-period').value};
    if (body.period === 'range') {
      body.start_date = $('tournament-start').value || null;
      body.end_date = $('tournament-end').value || null;
    }
    const tournament = await api(base, {method: 'POST', body});
    await load(tournament.id);
  });
}
