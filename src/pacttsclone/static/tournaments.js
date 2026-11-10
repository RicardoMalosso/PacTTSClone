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

function clipIdentity(clip, label) {
  const identity = document.createElement('div');
  identity.className = 'tournament-clip-identity';
  if (clip.thumbnail_url) {
    const picture = document.createElement('img');
    picture.src = clip.thumbnail_url;
    picture.alt = '';
    picture.loading = 'lazy';
    identity.append(picture);
  }
  const details = document.createElement('div');
  details.append(label);
  const {wins, losses, gold, silver, bronze} = clip.record;
  const stats = document.createElement('div');
  stats.className = 'muted';
  stats.textContent = wins + ' W / ' + losses + ' L';
  stats.title = 'Host picks across tournaments.';
  if (wins) {
    for (const [count, icon, medal] of [
      [gold, '🥇', 'gold'], [silver, '🥈', 'silver'], [bronze, '🥉', 'bronze'],
    ]) {
      if (!count) continue;
      const award = document.createElement('span');
      award.textContent = ' ' + icon + ' ' + count;
      award.title = count + ' ' + medal + ' medals';
      award.setAttribute('aria-label', award.title);
      stats.append(award);
    }
  }
  details.append(stats);
  identity.append(details);
  return identity;
}

function renderResults(rows, bracket) {
  const labels = new Map(bracket.clips.map(({id}, index) => [id, 'Clip ' + (index + 1)]));
  const clips = new Map(bracket.clips.map(clip => [clip.id, clip]));
  const ranking = $('tournament-ranking');
  ranking.replaceChildren();
  for (const row of rows) {
    const item = document.createElement('li');
    const label = labels.get(row.clip);
    item.title = row.provisional
      ? 'Provisional until this clip has five counted comparisons.'
      : 'Placement is based on counted head-to-head choices.';
    item.append(clipIdentity(clips.get(row.clip), label), row.comparisons + ' comparisons',
      row.provisional ? ' · Provisional' : '', audio(row.clip, label));
    ranking.append(item);
  }
  $('tournament-ranking-empty').hidden = rows.length > 0;

  const roster = $('tournament-clips');
  roster.replaceChildren();
  for (const clip of bracket.clips) {
    const item = document.createElement('li');
    const label = labels.get(clip.id);
    item.append(clipIdentity(clip, label));
    if (clip.tag) {
      item.title = 'Tagged locally by the host.';
      item.append(' · ' + clip.tag);
    }
    if (clip.playable) item.append(audio(clip.id, label));
    else item.append(' · MP3 unavailable');
    roster.append(item);
  }

  const graphic = $('tournament-bracket');
  graphic.replaceChildren();
  $('tournament-show-bracket').textContent = bracket.slots ? 'Bracket' : 'Match history';
  $('tournament-bracket-heading').textContent = bracket.slots
    ? 'Elimination bracket' : 'Head-to-head match history';
  if (bracket.slots) {
    const depth = Math.max(...bracket.slots.map(slot => slot.round));
    for (let level = depth; level >= 1; level--) {
      const column = document.createElement('section');
      const heading = document.createElement('h3');
      heading.textContent = level === 1 ? 'Final' : 'Round ' + (depth - level + 1);
      column.append(heading);
      for (const slot of bracket.slots.filter(match => match.round === level)) {
        const card = document.createElement('div');
        card.className = 'tournament-match';
        const contestants = document.createElement('div');
        contestants.className = 'tournament-contenders';
        for (const id of [slot.a, slot.b]) {
          const side = document.createElement('div');
          if (clips.has(id)) side.append(clipIdentity(clips.get(id), labels.get(id)));
          else side.textContent = slot.resolved ? 'Empty slot' : 'Awaiting entrant';
          contestants.append(side);
        }
        card.classList.add('tournament-elimination-match');
        const outcome = document.createElement('div');
        outcome.textContent = slot.winner
          ? labels.get(slot.winner) + (slot.played ? ' won' : ' advances by walkover')
          : slot.resolved ? 'No entrant advances' : 'Pending';
        card.append(contestants, outcome);
        column.append(card);
      }
      graphic.append(column);
    }
    return labels;
  }
  if (!bracket.matches.length) graphic.textContent = 'No matchups yet.';
  for (const match of bracket.matches) {
    const card = document.createElement('div');
    card.className = 'tournament-match';
    const sides = document.createElement('div');
    for (const side of ['a', 'b']) {
      const slot = document.createElement('div');
      slot.className = 'tournament-slot';
      slot.append(clipIdentity(clips.get(match[side]), labels.get(match[side])));
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
    panel.textContent = bracket.champion
      ? 'Champion: ' + labels.get(bracket.champion) : 'No more matchups available.';
    return;
  }

  const vote = async result => {
    await api(endpoint + '/vote', {method: 'POST', body: {match_id: match.id, result}});
    await refreshMatch();
  };
  const contenders = document.createElement('div');
  contenders.className = 'tournament-contenders';
  panel.append(contenders);
  for (const side of ['a', 'b']) {
    const clip = match[side];
    const label = side.toUpperCase();
    const group = document.createElement('div');
    const entry = bracket.clips.find(item => item.id === clip);
    const tagButton = button('Terrible horrible (' + label + ')',
      'Tag this clip without changing the result or advancing the bracket.', async () => {
        const report = await api(endpoint + '/report/' + encodeURIComponent(clip), {method: 'POST'});
        entry.tag = report.tag;
        tagButton.setAttribute('aria-pressed', 'true');
        tagButton.disabled = true;
        renderResults(rows, bracket);
        $('tournament-status').textContent = 'Clip tagged · ' + report.tag;
      });
    tagButton.disabled = Boolean(entry.tag);
    tagButton.setAttribute('aria-pressed', String(Boolean(entry.tag)));
    group.append(
      clipIdentity(entry, label + ' · ' + labels.get(clip)),
      audio(clip, 'Clip ' + label),
      button('Pick ' + label, 'Count a local win for Clip ' + label + '.', () => vote(side)),
      tagButton,
    );
    contenders.append(group);
  }
  if (!bracket.slots) {
    panel.append(button('Skip', 'Move to the next matchup without awarding a win.', () => vote('skip')));
  }
  panel.append(
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
    winners: 'Previous Winners', all: 'All', month: 'Last month', short: 'Random draft'};
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
    $('tournament-draft-options').hidden = $('tournament-period').value !== 'short';
  };
  $('tournament-select').onchange = () => run(refreshMatch);
  $('tournament-create').onclick = () => run(async () => {
    const body = {period: $('tournament-period').value, mode: $('tournament-mode').value};
    if (body.period === 'short') body.draft_size = Number($('tournament-draft-size').value);
    if (body.period === 'range') {
      body.start_date = $('tournament-start').value || null;
      body.end_date = $('tournament-end').value || null;
    }
    const tournament = await api(base, {method: 'POST', body});
    await load(tournament.id);
  });
}
