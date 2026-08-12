/** @type {import("jest").Config} */
module.exports = {
  collectCoverageFrom: [
    "src/**/*.ts",
    "!src/**/*.test.ts",
    "!src/journey/apiTypes.ts",
    // The translation catalog is presentation data with dynamic DOM coverage in the Web E2E gate.
    "!src/i18n/catalog.ts",
    // Tokyo locale copy is presentation data exercised through the CP-206 EN/JA/ZH Web E2E gate.
    "!src/tokyo/copy.ts",
    // Tokyo API/domain contracts are type-only and contain no runtime behaviour.
    "!src/tokyo/types.ts",
  ],
  coverageDirectory: "coverage",
  coverageProvider: "v8",
  coverageThreshold: {
    global: {
      branches: 100,
      functions: 100,
      lines: 100,
      statements: 100,
    },
  },
  testEnvironment: "node",
  testMatch: ["<rootDir>/src/**/*.test.ts"],
  transform: {
    "^.+\\.ts$": [
      "babel-jest",
      {
        presets: [
          ["@babel/preset-env", { targets: { node: "current" } }],
          "@babel/preset-typescript",
        ],
      },
    ],
  },
};
