/**
 * Agent and Endpoint Configuration
 * 
 * This file defines the internal data structure for agents and their endpoints.
 * Each endpoint can be accessed via HTML (product page) or JSON (proxied data).
 * 
 * Agent Structure:
 * - groups: Array of endpoint groups (INTERNAL ONLY - not exposed to frontend)
 * 
 * Group Structure (INTERNAL BACKEND DETAIL):
 * Groups are used internally to organize endpoints with different baseURLs.
 * They are NOT shown on the frontend - users only see a flat list of endpoints.
 * - id: Unique identifier for the group
 * - name: Display name (used internally only)
 * - baseUrl: Base URL for all endpoints in this group
 * - endpoints: Array of endpoint definitions
 * 
 * Endpoint Structure:
 * - upstreamUrl: Can be a full URL OR a path (combined with group's baseUrl)
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Load agents from JSON file
let agents = [];
try {
  const agentsData = readFileSync(join(__dirname, 'agents.json'), 'utf-8');
  agents = JSON.parse(agentsData);
} catch (error) {
  console.error('Error loading agents.json:', error.message);
  agents = [];
}

export { agents };

/**
 * Get all agents
 */
export function getAllAgents() {
  return agents;
}

/**
 * Get agent by ID
 */
export function getAgentById(agentId) {
  return agents.find(agent => agent.id === agentId);
}

/**
 * Get endpoint by path
 */
export function getEndpointByPath(path) {
  for (const agent of agents) {
    for (const group of (agent.groups || [])) {
      const endpoint = group.endpoints.find(ep => ep.path === path);
      if (endpoint) {
        return { agent, group, endpoint };
      }
    }
  }
  return null;
}

/**
 * Get all endpoints across all agents and groups
 * Note: Groups are internal - not exposed in the returned data
 */
export function getAllEndpoints() {
  const allEndpoints = [];
  for (const agent of agents) {
    for (const group of (agent.groups || [])) {
      for (const endpoint of group.endpoints) {
        allEndpoints.push({
          ...endpoint,
          agentId: agent.id,
          agentName: agent.name,
          agentIcon: agent.icon
        });
      }
    }
  }
  return allEndpoints;
}

/**
 * Build full upstream URL for an endpoint
 * Combines group baseUrl with endpoint upstreamUrl
 * 
 * @param {Object} group - The group object
 * @param {Object} endpoint - The endpoint object
 * @returns {string} Full upstream URL
 */
export function buildUpstreamUrl(group, endpoint) {
  const upstreamUrl = endpoint.upstreamUrl || '';
  
  // If upstreamUrl is already a full URL (starts with http:// or https://), use it as-is
  if (upstreamUrl.startsWith('http://') || upstreamUrl.startsWith('https://')) {
    return upstreamUrl;
  }
  
  // Otherwise, combine group baseUrl with endpoint upstreamUrl
  const baseUrl = (group.baseUrl || '').replace(/\/+$/, ''); // Strip trailing slashes
  const path = upstreamUrl.startsWith('/') ? upstreamUrl : `/${upstreamUrl}`;
  
  return baseUrl + path;
}

/**
 * Generate example request URL from endpoint path and parameters
 * 
 * @param {Object} endpoint - The endpoint object
 * @returns {string} Example request path with query parameters
 */
export function generateExampleRequest(endpoint) {
  const path = endpoint.path || '';
  const parameters = endpoint.parameters || '';
  
  // If no parameters, just return the path
  if (!parameters) {
    return path;
  }
  
  // If parameters is a string, append it to the path
  // It should be in the format: "param1=value1&param2=value2" or "?param1=value1&param2=value2"
  const queryString = parameters.startsWith('?') ? parameters : `?${parameters}`;
  
  return `${path}${queryString}`;
}

/**
 * Get all groups for an agent
 */
export function getAgentGroups(agentId) {
  const agent = getAgentById(agentId);
  return agent ? agent.groups || [] : [];
}

