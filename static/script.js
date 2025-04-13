let userId = localStorage.getItem("user_id") || null;
let playerName = "";
let restaurantName = "";

async function postMessage(message) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, message }),
  });
  const data = await res.json();

  if (data.response) {
    document.getElementById("chatLog").innerHTML += `<p><strong>You:</strong> ${message}</p>`;
    document.getElementById("chatLog").innerHTML += `<p><strong>AI:</strong> ${data.response}</p>`;
    updateState(data);
  } else {
    alert("Error: " + data.error);
  }
}

function updateState(data) {
  document.getElementById("playerName").textContent = data.player;
  document.getElementById("restaurantName").textContent = data.restaurant;
  document.getElementById("gameDay").textContent = data.day;
  document.getElementById("playerMoney").textContent = data.money.toFixed(2);

  const list = document.getElementById("inventoryList");
  list.innerHTML = "";
  for (let item in data.inventory) {
    const li = document.createElement("li");
    li.textContent = `${item}: ${data.inventory[item]}`;
    list.appendChild(li);
  }
}

document.getElementById("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("messageInput");
  const msg = input.value.trim();
  if (msg) {
    await postMessage(msg);
    input.value = "";
  }
});
