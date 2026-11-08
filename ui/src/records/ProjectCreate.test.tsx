import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ProjectPicker } from './ProjectPicker';
import { setCurrentProject } from './project';
import { setLanguage, texts } from '../i18n';

it('creates from loose files without asking for a name', async () => {
  setLanguage('en'); setCurrentProject(undefined);
  const fetch = vi.fn(async (url: unknown, init?: RequestInit) => {
    if (String(url) === '/api/projects' && init?.method === 'POST') return Response.json({ id: 'sample', name: 'Project 2026-11-08', created_at: '' });
    return Response.json({ projects: [] });
  });
  vi.stubGlobal('fetch', fetch);
  render(<ProjectPicker onClose={() => {}} files={1} />);
  fireEvent.click(await screen.findByRole('button', { name: texts.newProject.en }));
  await waitFor(() => expect(fetch.mock.calls.some(([url, init]) => String(url) === '/api/projects' && init?.method === 'POST')).toBe(true));
  const call = fetch.mock.calls.find(([, init]) => init?.method === 'POST')!;
  expect(JSON.parse(String(call[1]?.body))).toEqual({});
  expect(screen.queryByRole('textbox', { name: texts.projectName.en })).toBeNull();
  vi.unstubAllGlobals();
});
