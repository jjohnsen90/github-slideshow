"use strict";

/* ============================================================
   Yahtzee — single-player, 13 turns
   Categories, scoring rules, dice holding, and live preview.
   ============================================================ */

// Pip layout per die face (which grid cells get a pip).
const PIP_LAYOUT = {
  1: ["mc"],
  2: ["tl", "br"],
  3: ["tl", "mc", "br"],
  4: ["tl", "tr", "bl", "br"],
  5: ["tl", "tr", "mc", "bl", "br"],
  6: ["tl", "tr", "ml", "mr", "bl", "br"],
};

const UPPER = [
  { key: "ones", label: "Ones", face: 1 },
  { key: "twos", label: "Twos", face: 2 },
  { key: "threes", label: "Threes", face: 3 },
  { key: "fours", label: "Fours", face: 4 },
  { key: "fives", label: "Fives", face: 5 },
  { key: "sixes", label: "Sixes", face: 6 },
];

const LOWER = [
  { key: "threeKind", label: "Three of a Kind", sub: "Sum of all dice" },
  { key: "fourKind", label: "Four of a Kind", sub: "Sum of all dice" },
  { key: "fullHouse", label: "Full House", sub: "Scores 25" },
  { key: "smallStraight", label: "Small Straight", sub: "Scores 30" },
  { key: "largeStraight", label: "Large Straight", sub: "Scores 40" },
  { key: "yahtzee", label: "Yahtzee", sub: "Scores 50" },
  { key: "chance", label: "Chance", sub: "Sum of all dice" },
];

const ALL_CATS = [...UPPER, ...LOWER];

// ---------- Scoring functions ----------
function counts(dice) {
  const c = [0, 0, 0, 0, 0, 0, 0]; // index = face value
  dice.forEach((d) => c[d]++);
  return c;
}
const sum = (dice) => dice.reduce((a, b) => a + b, 0);

function scoreUpper(face, dice) {
  return counts(dice)[face] * face;
}

function hasNOfKind(dice, n) {
  return counts(dice).some((cnt) => cnt >= n);
}

function isFullHouse(dice) {
  const c = counts(dice).filter((x) => x > 0).sort();
  // Either exactly 2+3, or five-of-a-kind (counts as full house in most rule sets)
  if (c.length === 2 && c[0] === 2 && c[1] === 3) return true;
  return false;
}

function hasStraight(dice, len) {
  const present = [...new Set(dice)].sort((a, b) => a - b);
  let run = 1;
  let best = 1;
  for (let i = 1; i < present.length; i++) {
    run = present[i] === present[i - 1] + 1 ? run + 1 : 1;
    best = Math.max(best, run);
  }
  return best >= len;
}

// Returns the score a category would earn for the given dice.
function potentialScore(key, dice) {
  switch (key) {
    case "ones": return scoreUpper(1, dice);
    case "twos": return scoreUpper(2, dice);
    case "threes": return scoreUpper(3, dice);
    case "fours": return scoreUpper(4, dice);
    case "fives": return scoreUpper(5, dice);
    case "sixes": return scoreUpper(6, dice);
    case "threeKind": return hasNOfKind(dice, 3) ? sum(dice) : 0;
    case "fourKind": return hasNOfKind(dice, 4) ? sum(dice) : 0;
    case "fullHouse": return isFullHouse(dice) ? 25 : 0;
    case "smallStraight": return hasStraight(dice, 4) ? 30 : 0;
    case "largeStraight": return hasStraight(dice, 5) ? 40 : 0;
    case "yahtzee": return hasNOfKind(dice, 5) ? 50 : 0;
    case "chance": return sum(dice);
    default: return 0;
  }
}

// ---------- Game state ----------
const state = {
  dice: [1, 2, 3, 4, 5],
  held: [false, false, false, false, false],
  rollsLeft: 3,
  scores: {},          // key -> number (locked)
  yahtzeeBonus: 0,
  turnsLeft: 13,
  hasRolledThisTurn: false,
};

// ---------- DOM ----------
const $ = (id) => document.getElementById(id);
const tray = $("dice-tray");
const rollBtn = $("roll-btn");
const hintEl = $("hint");

function newGame() {
  state.dice = [1, 2, 3, 4, 5];
  state.held = [false, false, false, false, false];
  state.rollsLeft = 3;
  state.scores = {};
  state.yahtzeeBonus = 0;
  state.turnsLeft = 13;
  state.hasRolledThisTurn = false;
  $("gameover").hidden = true;
  buildDice();
  buildScorecard();
  render();
  hintEl.textContent = "Roll to start your turn. Click dice to hold them.";
}

function buildDice() {
  tray.innerHTML = "";
  for (let i = 0; i < 5; i++) {
    const die = document.createElement("button");
    die.className = "die disabled";
    die.type = "button";
    die.dataset.index = i;
    die.setAttribute("aria-label", `Die ${i + 1}`);
    die.addEventListener("click", () => toggleHold(i));
    tray.appendChild(die);
  }
}

function renderDie(i) {
  const die = tray.children[i];
  const value = state.dice[i];
  die.innerHTML = "";
  PIP_LAYOUT[value].forEach((pos) => {
    const pip = document.createElement("span");
    pip.className = `pip ${pos}`;
    die.appendChild(pip);
  });
  die.classList.toggle("held", state.held[i]);
  // Dice are only interactive after the first roll and before the turn ends.
  const interactive = state.hasRolledThisTurn && state.rollsLeft > 0;
  die.classList.toggle("disabled", !interactive);
  die.setAttribute(
    "aria-label",
    `Die ${i + 1}, showing ${value}.${state.held[i] ? " Held." : ""}` +
      (interactive ? " Click to " + (state.held[i] ? "release." : "hold.") : "")
  );
}

function toggleHold(i) {
  if (!state.hasRolledThisTurn || state.rollsLeft === 0) return;
  state.held[i] = !state.held[i];
  renderDie(i);
}

function rollDice() {
  if (state.rollsLeft === 0) return;
  state.hasRolledThisTurn = true;
  for (let i = 0; i < 5; i++) {
    if (!state.held[i]) {
      state.dice[i] = 1 + Math.floor(Math.random() * 6);
      const die = tray.children[i];
      die.classList.remove("rolling");
      void die.offsetWidth; // restart animation
      die.classList.add("rolling");
    }
  }
  state.rollsLeft--;
  render();
  hintEl.textContent =
    state.rollsLeft > 0
      ? "Hold dice you want to keep, then roll again — or pick a category to score."
      : "No rolls left. Choose a category to score this turn.";
}

function buildScorecard() {
  renderList("upper-list", UPPER);
  renderList("lower-list", LOWER);
}

function renderList(listId, cats) {
  const ul = $(listId);
  ul.innerHTML = "";
  cats.forEach((cat) => {
    const li = document.createElement("li");
    li.className = "score-row";
    li.dataset.key = cat.key;
    li.tabIndex = 0;
    li.innerHTML =
      `<span class="label">${cat.label}` +
      (cat.sub ? `<small>${cat.sub}</small>` : "") +
      `</span><span class="value"></span>`;
    li.addEventListener("click", () => chooseCategory(cat.key));
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        chooseCategory(cat.key);
      }
    });
    ul.appendChild(li);
  });
}

function chooseCategory(key) {
  // Can only score after rolling at least once this turn, and only once per category.
  if (!state.hasRolledThisTurn) return;
  if (key in state.scores) return;

  let gained = potentialScore(key, state.dice);

  // Yahtzee bonus: a second+ scoring Yahtzee earns +100 (if the Yahtzee box was already a 50).
  if (
    hasNOfKind(state.dice, 5) &&
    state.scores.yahtzee === 50 &&
    key !== "yahtzee"
  ) {
    state.yahtzeeBonus += 100;
  }

  state.scores[key] = gained;
  state.turnsLeft--;

  // Reset for next turn.
  state.held = [false, false, false, false, false];
  state.rollsLeft = 3;
  state.hasRolledThisTurn = false;

  render();

  if (state.turnsLeft === 0) {
    endGame();
  } else {
    hintEl.textContent = "Scored! Roll to start your next turn.";
  }
}

// ---------- Totals ----------
function upperSubtotal() {
  return UPPER.reduce((t, c) => t + (state.scores[c.key] || 0), 0);
}
function upperBonus() {
  return upperSubtotal() >= 63 ? 35 : 0;
}
function lowerSubtotal() {
  return LOWER.reduce((t, c) => t + (state.scores[c.key] || 0), 0);
}
function grandTotal() {
  return (
    upperSubtotal() + upperBonus() + lowerSubtotal() + state.yahtzeeBonus
  );
}

function render() {
  for (let i = 0; i < 5; i++) renderDie(i);

  rollBtn.disabled = state.rollsLeft === 0;
  rollBtn.textContent =
    state.rollsLeft === 3 ? "Roll Dice" : `Roll Again (${state.rollsLeft})`;
  $("rolls-left").textContent = state.rollsLeft;

  ALL_CATS.forEach((cat) => {
    const li = document.querySelector(`[data-key="${cat.key}"]`);
    const valEl = li.querySelector(".value");
    li.classList.remove("available", "locked");
    valEl.classList.remove("zero");

    if (cat.key in state.scores) {
      li.classList.add("locked");
      li.tabIndex = -1;
      valEl.textContent = state.scores[cat.key];
    } else if (state.hasRolledThisTurn) {
      li.classList.add("available");
      li.tabIndex = 0;
      const p = potentialScore(cat.key, state.dice);
      valEl.textContent = p;
      if (p === 0) valEl.classList.add("zero");
    } else {
      li.tabIndex = -1;
      valEl.textContent = "";
    }
  });

  $("upper-bonus").textContent = upperBonus();
  $("upper-total").textContent = upperSubtotal() + upperBonus();
  $("yahtzee-bonus").textContent = state.yahtzeeBonus;
  $("lower-total").textContent = lowerSubtotal() + state.yahtzeeBonus;
  $("grand-total").textContent = grandTotal();
}

function endGame() {
  const total = grandTotal();
  $("final-score").textContent = total;
  let msg;
  if (total >= 300) msg = "Incredible — that's a championship score!";
  else if (total >= 250) msg = "Excellent rolling!";
  else if (total >= 200) msg = "Solid game. Well played.";
  else if (total >= 150) msg = "Not bad — the dice were fair to you.";
  else msg = "The dice were stingy this time. Run it back!";
  $("final-msg").textContent = msg;
  $("gameover").hidden = false;
}

// ---------- Wire up ----------
rollBtn.addEventListener("click", rollDice);
$("new-game").addEventListener("click", newGame);
$("play-again").addEventListener("click", newGame);

newGame();
