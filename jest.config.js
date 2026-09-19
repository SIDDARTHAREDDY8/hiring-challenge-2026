/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/tests/typescript/**/*.test.ts'],
  moduleFileExtensions: ['ts', 'js', 'json'],
};
