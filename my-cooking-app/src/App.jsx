import { useState, useEffect, useRef } from "react";
import "./App.css";

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const chatEndRef = useRef(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const newMessages = [...messages, { role: "user", text: input }];
    setMessages(newMessages);

    const conversationHistory = newMessages.slice(-6);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input,
          history: conversationHistory,
        }),
      });

      const data = await res.json();
      let reply = data.reply;

      // 🧠 Detect markdown code blocks with JSON
      let formattedJson = null;
      let isJson = false;

      const codeBlockMatch = typeof reply === "string" && reply.match(/```json([\s\S]*?)```/i);
      if (codeBlockMatch) {
        try {
          const jsonStr = codeBlockMatch[1].trim();
          const obj = JSON.parse(jsonStr);
          formattedJson = JSON.stringify(obj, null, 2);
          isJson = true;
          reply = ""; // Hide raw text
        } catch (err) {
          console.error("❌ Failed to parse JSON block:", err);
        }
      } 
      // if backend already returns parsed JSON (not string)
      else if (typeof reply === "object") {
        formattedJson = JSON.stringify(reply, null, 2);
        isJson = true;
        reply = "";
      }

      setMessages([
        ...newMessages,
        { role: "agent", text: reply, formattedJson, isJson },
      ]);
    } catch (err) {
      console.error("⚠️ Error fetching:", err);
      setMessages([
        ...newMessages,
        { role: "agent", text: "Something went wrong. Try again.", isJson: false },
      ]);
    }

    setInput("");
  };

  // 🌈 Simple syntax highlighter for JSON
  const highlightJSON = (jsonString) => {
    if (!jsonString) return "";
    return jsonString
      .replace(/(&)/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(
        /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        (match) => {
          let cls = "number";
          if (/^"/.test(match)) {
            cls = /:$/.test(match) ? "key" : "string";
          } else if (/true|false/.test(match)) {
            cls = "boolean";
          } else if (/null/.test(match)) {
            cls = "null";
          }
          return `<span class="${cls}">${match}</span>`;
        }
      );
  };

  return (
    <div className="chat-container">
      <h2>🥘 Recipe Chatbot</h2>

      <div className="chat-box">
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <div className="sender">
              {m.role === "user" ? "🧑 You" : "🤖 Agent"}
            </div>

            {m.isJson ? (
              (() => {
                try {
                  const recipeData = JSON.parse(m.formattedJson);
                  const recipe = recipeData.recipes?.[0];
                  if (!recipe) throw new Error("No recipe found");

                  // Extract known fields
                  const {
                    name,
                    ingredients,
                    instructions,
                    cookingTime,
                    difficulty,
                    nutrition,
                    ...otherInfo
                  } = recipe;

                  return (
                    <div className="recipe-card">
                      <h3 className="recipe-title">🍽️ {name}</h3>

                      {(cookingTime || difficulty) && (
                        <div className="recipe-meta">
                          {cookingTime && <p><strong>⏱ Cooking Time:</strong> {cookingTime}</p>}
                          {difficulty && <p><strong>🎯 Difficulty:</strong> {difficulty}</p>}
                        </div>
                      )}

                      {ingredients && ingredients.length > 0 && (
                        <div className="recipe-section">
                          <h4>🧂 Ingredients</h4>
                          <ul>
                            {ingredients.map((ing, i) => (
                              <li key={i}>{ing}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {instructions && instructions.length > 0 && (
                        <div className="recipe-section">
                          <h4>👩‍🍳 Instructions</h4>
                          <ol>
                            {instructions.map((step, i) => (
                              <li key={i}>Step {i + 1}: {step}</li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {nutrition && (
                        <div className="recipe-section">
                          <h4>🥗 Nutrition</h4>
                          <ul>
                            {Object.entries(nutrition).map(([k, v]) => (
                              <li key={k}>
                                <strong>{k.charAt(0).toUpperCase() + k.slice(1)}:</strong> {v}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {Object.keys(otherInfo).length > 0 && (
                        <div className="recipe-section">
                          <h4>📘 Other Info</h4>
                          <ul>
                            {Object.entries(otherInfo).map(([k, v]) => (
                              <li key={k}>
                                <strong>{k.charAt(0).toUpperCase() + k.slice(1)}:</strong>{" "}
                                {typeof v === "object" ? JSON.stringify(v, null, 2) : String(v)}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  );
                } catch (err) {
                  console.error("Invalid recipe JSON:", err);
                  return (
                    <pre
                      className="json-bubble"
                      dangerouslySetInnerHTML={{
                        __html: highlightJSON(m.formattedJson),
                      }}
                    ></pre>
                  );
                }
              })()
            ) : (
              <div className="message-bubble text-bubble">{m.text}</div>
            )}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      <div className="input-box">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
        />
        <button onClick={sendMessage}>Send</button>
      </div>
    </div>
  );
}

export default App;
