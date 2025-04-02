function sendInput() {
    let input = document.getElementById("inputBox").value;
    fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("responseArea").innerText = data.response;
    })
    .catch(error => console.error("Error:", error));
}
