const fs = require("fs");
const path = require("path");

const [, , entrypointArg, hostArg, portArg, stdoutPath, stderrPath] = process.argv;

if (!entrypointArg) {
  throw new Error("Missing platform server entrypoint argument.");
}

if (hostArg) process.env.HOST = hostArg;
if (portArg) process.env.PORT = portArg;

function redirectStream(stream, filePath) {
  if (!filePath) return;
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const file = fs.createWriteStream(filePath, { flags: "a" });
  const originalWrite = stream.write.bind(stream);
  stream.write = (chunk, encoding, callback) => {
    if (typeof encoding === "function") {
      callback = encoding;
      encoding = undefined;
    }
    file.write(chunk, encoding);
    if (callback) callback();
    return true;
  };
}

redirectStream(process.stdout, stdoutPath);
redirectStream(process.stderr, stderrPath);

require(path.resolve(entrypointArg));
