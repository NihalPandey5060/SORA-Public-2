  import React, { useEffect, useRef, useState } from "react";

  const defaultWsBase = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname || "localhost"}:8000/ws`;
  const WS_URL = `${import.meta.env.VITE_WEBSOCKET_URL || defaultWsBase}/media`;
  const MEDIA_BASE_URL = WS_URL.replace(/^ws/, "http").replace(/\/ws\/media$/, "/media");


  function RegistrationModal({ onClose, wsRef, clientIdRef, conversationIdRef }) {
  const [step, setStep] = useState("username"); // skip confirm, start here
  const [username, setUsername] = useState("");
  const [photos, setPhotos] = useState([]);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    if (step !== "capture") return;
    (async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    })();
    return () => streamRef.current?.getTracks().forEach((t) => t.stop());
  }, [step]);

  const capturePhoto = () => {
    if (photos.length >= 5) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const base64 = canvas.toDataURL("image/webp", 0.8).split(",")[1];
    const next = [...photos, base64];
    setPhotos(next);
    if (next.length === 5) sendToBackend(next);
  };

  const sendToBackend = (capturedPhotos) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({
      type: "user_verification",
      timestamp: Date.now(),
      id: clientIdRef.current,
      payload: {
        username,
        photos: capturedPhotos.map((data, i) => ({ index: i + 1, format: "webp", data })),
      },
      metadata: { conversation_id: conversationIdRef.current, trigger: "popup_yes" },
    }));
    streamRef.current?.getTracks().forEach((t) => t.stop());
    setStep("done");
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "#fff", padding: "2rem", borderRadius: "12px", width: "380px", maxWidth: "90vw", textAlign: "center", boxShadow: "0 4px 20px rgba(0,0,0,0.3)" }}>

        {step === "username" && (
          <>
            <h2 style={{ marginTop: 0 }}>Enter your name</h2>
            <input
              type="text" placeholder="Your name..." value={username} autoFocus
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && username.trim() && setStep("capture")}
              style={{ width: "100%", padding: "8px 12px", borderRadius: "6px", border: "1px solid #ccc", fontSize: "1rem", marginBottom: "1rem", boxSizing: "border-box" }}
            />
            <button disabled={!username.trim()} onClick={() => setStep("capture")}
              style={{ padding: "8px 28px", background: "#2196F3", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", fontSize: "1rem", opacity: username.trim() ? 1 : 0.5 }}>
              Next
            </button>
          </>
        )}

        {step === "capture" && (
          <>
            <h2 style={{ marginTop: 0 }}>Take 5 photos, {username}</h2>
            <video ref={videoRef} autoPlay muted playsInline style={{ width: "100%", borderRadius: "8px", marginBottom: "0.75rem", background: "#000" }} />
            <canvas ref={canvasRef} style={{ display: "none" }} />
            <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginBottom: "0.75rem" }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} style={{ width: "32px", height: "32px", borderRadius: "6px", background: i < photos.length ? "#4CAF50" : "#eee", color: i < photos.length ? "#fff" : "#999", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "13px", fontWeight: 500 }}>
                  {i + 1}
                </div>
              ))}
            </div>
            <p style={{ fontSize: "13px", color: "#666", margin: "0 0 0.75rem" }}>{photos.length} of 5 captured</p>
            <button onClick={capturePhoto} disabled={photos.length >= 5}
              style={{ padding: "8px 28px", background: "#2196F3", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", fontSize: "1rem", opacity: photos.length >= 5 ? 0.5 : 1 }}>
              Capture photo ({photos.length}/5)
            </button>
          </>
        )}

        {step === "done" && (
          <>
            <h2 style={{ marginTop: 0 }}>All done!</h2>
            <p>5 photos sent for <strong>{username}</strong>.</p>
            <button onClick={onClose} style={{ padding: "8px 24px", background: "#4CAF50", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", fontSize: "1rem" }}>
              OK
            </button>
          </>
        )}

      </div>
    </div>
  );
} 

  function App() {
    const [connected, setConnected] = useState(false);
    const [audioRecording, setAudioRecording] = useState(false);
    const [videoRecording, setVideoRecording] = useState(false);
    const [status, setStatus] = useState("Idle");
    const fps = 5;
    const videoIntervalRef = useRef(null);
    const [textMessage, setTextMessage] = useState("");
    const wsRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const chunkIndexRef = useRef(0);
    const [showRegistration, setShowRegistration] = useState(false);
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const chatContainerRef = useRef(null);
    const [popup, setPopup] = useState(null);
    const [mouthViseme, setMouthViseme] = useState(0);
    const [visemeStatus, setVisemeStatus] = useState("Idle");
    const visemePollRef = useRef(null);
    const visemeTimersRef = useRef([]);

    const clientIdRef = useRef(
      window.crypto?.randomUUID?.() || `client_${Date.now()}` // we can generate this id from the backend after authentication, user will get unique id after connection
    );
    const conversationIdRef = useRef(`conv_${Date.now()}`);

    const handleAddMessageToChat = (message, from = "user") => {
      const chatContainer = chatContainerRef.current;
      if (!chatContainer) return;
      const chatMessageElem = document.createElement("div");
      chatMessageElem.className = `message_from_${from}`;
      const chatMessageSpan = document.createElement("span");
      chatMessageSpan.style.background = from === "user" ? "#DCF8C6" : "#E5E5EA";
      chatMessageSpan.style.padding = "8px 12px";
      chatMessageSpan.style.borderRadius = "5px";
      chatMessageSpan.style.display = "inline-block";
      chatMessageSpan.style.maxWidth = "80%";
      chatMessageSpan.style.wordWrap = "break-word";
      chatMessageSpan.textContent = message;
      chatMessageElem.appendChild(chatMessageSpan);
      chatContainer.appendChild(chatMessageElem);
      chatContainer.scrollTop = chatContainer.scrollHeight;
    };

    const clearVisemePlayback = () => {
      if (visemePollRef.current) {
        window.clearInterval(visemePollRef.current);
        visemePollRef.current = null;
      }

      visemeTimersRef.current.forEach((timerId) => window.clearTimeout(timerId));
      visemeTimersRef.current = [];
      setMouthViseme(0);
    };

    const playVisemes = (visemes) => {
      clearVisemePlayback();
      setVisemeStatus("Playing visemes");

      visemeTimersRef.current = visemes.map(({ offset_ms, viseme_id }) =>
        window.setTimeout(() => {
          setMouthViseme(viseme_id);
        }, Math.max(0, Number(offset_ms) || 0))
      );

      const lastOffset = visemes.reduce(
        (maxOffset, item) => Math.max(maxOffset, Number(item.offset_ms) || 0),
        0
      );

      const resetTimer = window.setTimeout(() => {
        setMouthViseme(0);
        setVisemeStatus("Visemes ready");
      }, lastOffset + 500);

      visemeTimersRef.current.push(resetTimer);
    };

    const pollForVisemes = (outputId) => {
      clearVisemePlayback();
      setVisemeStatus("Waiting for visemes");

      const visemeUrl = `${MEDIA_BASE_URL}/output/${outputId}/output.vsim.json`;
      const startedAt = Date.now();

      visemePollRef.current = window.setInterval(async () => {
        try {
          const response = await fetch(visemeUrl);
          if (!response.ok) {
            if (Date.now() - startedAt > 30000) {
              clearVisemePlayback();
              setVisemeStatus("Visemes unavailable");
            }
            return;
          }

          const visemes = await response.json();
          if (Array.isArray(visemes) && visemes.length > 0) {
            window.clearInterval(visemePollRef.current);
            visemePollRef.current = null;
            playVisemes(visemes);
          }
        } catch (error) {
          console.error("Failed to fetch visemes:", error);
          if (Date.now() - startedAt > 30000) {
            clearVisemePlayback();
            setVisemeStatus("Viseme fetch failed");
          }
        }
      }, 1000);
    };

    // -----------------------------
    // Handle Send Message (Chat)
    // -----------------------------
    const handleSendMessage = () => {
      if (!connected) return;
      const message = textMessage.trim();
      if (message === "") return;
      const packet = {
        type: "text_message",
        timestamp: Date.now(),
        id: clientIdRef.current,
        payload: {
          text: message,
          visemes: [],
        },
        metadata: {
          speaker: "user",
          conversation_id: conversationIdRef.current,
        },
      };
      if(wsRef.current.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(JSON.stringify(packet)); // send message over WebSocket
      handleAddMessageToChat(message, "user"); // add message to chat UI
      setTextMessage("");
    };
    // -----------------------------
    // WebSocket Setup
    // -----------------------------
    useEffect(() => {
      let closedByCleanup = false;
      let reconnectTimer = null;

      const connectWebSocket = () => {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;
        setStatus("WebSocket connecting...");

        ws.onopen = () => {
          if (wsRef.current !== ws) return;
          setConnected(true);
          setStatus("WebSocket connected");
          ws.send(JSON.stringify({ type: "init", session_id: clientIdRef.current }));
        };

        ws.onclose = () => {
          if (wsRef.current !== ws) return;
          setConnected(false);
          setStatus("WebSocket disconnected");
          wsRef.current = null;

          if (!closedByCleanup) {
            reconnectTimer = window.setTimeout(connectWebSocket, 1500);
          }
        };

        ws.onmessage = (event) => {
          if (wsRef.current !== ws) return;
          const jsonData = JSON.parse(event.data);
          console.log("Received message:", jsonData);
          if (jsonData.type === "text_message" && jsonData.payload) {
            handleAddMessageToChat(jsonData.payload.text, "avatar");
            if (jsonData.payload.output_id) {
              pollForVisemes(jsonData.payload.output_id);
            }
          }
          else if (jsonData.type === "error" && jsonData.payload) {
            const stage = jsonData.payload.stage || "pipeline";
            const message = jsonData.payload.message || "Unknown error";
            setVisemeStatus(`${stage}: ${message}`);
            handleAddMessageToChat(`Avatar pipeline error (${stage}): ${message}`, "avatar");
          }
          else if(jsonData.type=="Pop_up" && jsonData.payload){
            setPopup({
              title : jsonData.payload.title || "Warning",
              message : jsonData.payload.message
            })
          }
          else if(jsonData.type === "notification" && jsonData.payload) {
            alert(`Notification: ${jsonData.payload.message}`);
          }
        };

        ws.onerror = () => {
          if (wsRef.current !== ws) return;
          setStatus("WebSocket error");
        };
      };

      connectWebSocket();

      return () => {
        closedByCleanup = true;
        if (reconnectTimer) window.clearTimeout(reconnectTimer);
        clearVisemePlayback();
        wsRef.current?.close();
      };
    }, []);

    // -----------------------------
    // Start Audio Recording (Opus chunks)
    // -----------------------------
    const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const streamRef = useRef(null);

  function pcm16ToBase64(pcm16) {
    let binary = "";
    const bytes = new Uint8Array(pcm16.buffer);
    const chunkSize = 0x8000;

    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  }

  const startAudioRecording = async () => {
    if (!connected || audioRecording) return;

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioCtx = new AudioContext({ sampleRate: 48000 });
    const source = audioCtx.createMediaStreamSource(stream);

    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    source.connect(processor);

    audioCtxRef.current = audioCtx;
    processorRef.current = processor;
    streamRef.current = stream;

    setAudioRecording(true);
    setStatus("Recording PCM...");

    processor.onaudioprocess = (e) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

      const input = e.inputBuffer.getChannelData(0);
      const pcm16 = new Int16Array(input.length);

      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm16[i] = Math.round(s * 32767); // ✅ CRITICAL FIX
      }

      wsRef.current.send(JSON.stringify({
        type: "audio_chunk",
        timestamp: Date.now(),
        id: clientIdRef.current,
        payload: {
          audio: {
            format: "pcm_s16le",
            sample_rate: 48000,
            channels: 1,
            data: pcm16ToBase64(pcm16),
          },
        },
      }));
    };

    processor.connect(audioCtx.destination); // ❌ REMOVE IF YOU DON'T WANT MIC ECHO
  };



    // -----------------------------
    // Stop Audio Recording
    // -----------------------------
    const stopAudioRecording = () => {
    processorRef.current?.disconnect();
    audioCtxRef.current?.close();
    streamRef.current?.getTracks().forEach(t => t.stop());

    setAudioRecording(false);
    setStatus("Stopped recording");
  };


    // capture single frame
    const captureFrame = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;

      if (!video.videoWidth || !video.videoHeight) return null;

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      return canvas.toDataURL("image/webp", 0.8).split(",")[1];
    };

    // -----------------------------
    // Start Video Recording (image frames 5fps)
    // -----------------------------

    const startVideoRecording = async () => {
      if (!connected || videoRecording) return;

      setVideoRecording(true);
      setStatus("Recording video...");
      if(canvasRef.current) {
        canvasRef.current.hidden = false;
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
        audio: false,
      });

      videoRef.current.srcObject = stream;
      await videoRef.current.play();

      if (videoIntervalRef.current) {
        clearInterval(videoIntervalRef.current);
      }

      videoIntervalRef.current = setInterval(() => {
        if (
          !wsRef.current ||
          wsRef.current.readyState !== WebSocket.OPEN ||
          !videoRef.current?.srcObject
        ) {
          return;
        }

        const base64Data = captureFrame();
        if (!base64Data) return;

        wsRef.current.send(
          JSON.stringify({
            type: "video_frame",
            timestamp: Date.now(),
            id: clientIdRef.current,
            payload: {
              video: {
                format: "webp",
                fps: fps,
                data: base64Data,
              },
              visemes: [],
              text: "",
            },
            metadata: {
              speaker: "user",
              conversation_id: conversationIdRef.current,
            },
          })
        );
      }, 1000 / fps);
    };

    // -----------------------------
    // Stop Video Recording (image frames)
    // -----------------------------
    const stopVideoRecording = () => {
      if (videoIntervalRef.current) {
        clearInterval(videoIntervalRef.current);
        videoIntervalRef.current = null;
      }

      const video = videoRef.current;
      if (video?.srcObject) {
        video.srcObject.getTracks().forEach((track) => track.stop());
        video.srcObject = null;
      }

      if(canvasRef.current) {
        canvasRef.current.hidden = true;
      }
      setVideoRecording(false);
      setStatus("Stopped video recording");
    };


    useEffect(() => {
      return () => {
        stopAudioRecording();
        stopVideoRecording();
        clearVisemePlayback();
      };
    }, []);


    return (
      <main>
        <div
          style={{
            minHeight: "60vh",
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "center",
            gap: "1rem",
            fontFamily: "sans-serif",
          }}
        >
          <div className="audio_div">
            <h1>Audio Streaming (Opus Chunks)</h1>
            <p>WebSocket: {connected ? "Connected" : "Disconnected"}</p>
            <p>Status: {status}</p>

            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                disabled={!connected || audioRecording}
                onClick={startAudioRecording}
              >
                Start Recording
              </button>
              <button disabled={!audioRecording} onClick={stopAudioRecording}>
                Stop Recording
              </button>
            </div>

            <small>Streaming Opus audio chunks using your JSON format</small>
          </div>
          <div className="video_div">
            <h1>Video Streaming (image frames)</h1>
            <p>WebSocket: {connected ? "Connected" : "Disconnected"}</p>
            <p>Status: {status}</p>
            <video
              autoPlay
              muted
              hidden
              ref={videoRef}
              width={640}
              height={480}
            ></video>
            <canvas
              style={{
                border: "1px solid black",
                width: "640px",
                height: "480px",
              }}
              hidden
              ref={canvasRef}
            ></canvas>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                disabled={!connected || videoRecording}
                onClick={startVideoRecording}
              >
                Start Recording
              </button>
              <button disabled={!videoRecording} onClick={stopVideoRecording}>
                Stop Recording
              </button>
            </div>

            <small>Streaming video image frames using your JSON format</small>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: "10px",
          }}
        >
          <button
            onClick={() => {
              startAudioRecording();
              startVideoRecording();
            }}
          >
            Start Streaming
          </button>
          <button
            onClick={() => {
              stopAudioRecording();
              stopVideoRecording();
            }}
          >
            Stop Streaming
          </button>
        </div>

        <div className="chat_section">
          <h2>Chat With Ai</h2>
          <div className="avatar_mouth_panel">
            <div className="avatar_face">
              <div className="avatar_eye"></div>
              <div className="avatar_eye"></div>
              <div
                className="avatar_mouth"
                style={{
                  height: `${8 + Math.min(Number(mouthViseme) || 0, 21) * 1.2}px`,
                  borderRadius: mouthViseme > 0 ? "50%" : "999px",
                }}
              ></div>
            </div>
            <span>Viseme: {mouthViseme} | {visemeStatus}</span>
          </div>
          <div className="chat_box">
            <div ref={chatContainerRef} className="chat_container">
            </div>
          </div>
          <div className="chat_input_area">
            <input type="text" name="message" id="message" value={textMessage} onChange={(e) => setTextMessage(e.target.value)} />
            <button
              onClick={handleSendMessage}
              disabled={!textMessage.trim() || !connected}
            >
              Chat Now
            </button>
          </div>
        </div>
        {popup && (
          <div style={{
            position: "fixed", inset: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 1000,
          }}>
            <div style={{
              background: "#fff", padding: "2rem",
              borderRadius: "12px", minWidth: "300px",
              maxWidth: "400px", textAlign: "center",
              boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
            }}>
              <h2 style={{ marginTop: 0 }}>{popup.title}</h2>
              <p>{popup.message}</p>

              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                {/* ✅ YES — open registration flow */}
                <button
                  onClick={() => {
                    setPopup(null);
                    setShowRegistration(true);
                  }}
                  style={{
                    padding: "8px 28px", background: "#4CAF50",
                    color: "#fff", border: "none",
                    borderRadius: "6px", cursor: "pointer", fontSize: "1rem",
                  }}
                >
                  Yes
                </button>

                {/* ✅ NO — notify backend and close */}
                <button
                  onClick={() => {
                    setPopup(null);
                    if (wsRef.current?.readyState === WebSocket.OPEN) {
                      wsRef.current.send(JSON.stringify({
                        type: "popup_response",
                        timestamp: Date.now(),
                        id: clientIdRef.current,
                        payload: { response: "no" },
                        metadata: { conversation_id: conversationIdRef.current },
                      }));
                    }
                  }}
                  style={{
                    padding: "8px 28px", background: "#f44336",
                    color: "#fff", border: "none",
                    borderRadius: "6px", cursor: "pointer", fontSize: "1rem",
                  }}
                >
                  No
                </button>
              </div>

            </div>
          </div>
        )}

        {/* ✅ Registration modal — shown after user clicks Yes */}
        {showRegistration && (
          <RegistrationModal
            onClose={() => setShowRegistration(false)}
            wsRef={wsRef}
            clientIdRef={clientIdRef}
            conversationIdRef={conversationIdRef}
          />
        )}
      </main>
    );
  }

  export default App;
