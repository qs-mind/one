import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { FileDoc } from './FileDoc';
import { fakeSources } from '../../project/fake';
import { setLanguage } from '../../i18n';

test.each(['sample.jpeg', 'sample-plan.pdf'])('%s opens as a picture, zoom renders sharper and fit resets', async (name) => {
  setLanguage('en');
  const sources = fakeSources({files:[{id:'f',name,status:'read',note:null,replaces:null}],pages:{f:1}});
  sources.pageImage = vi.fn(sources.pageImage);
  render(<FileDoc sources={sources} fileId="f" />);
  await screen.findByRole('img');
  expect(screen.getByRole('radio', {name:'Picture'})).toHaveAttribute('aria-checked', 'true');
  fireEvent.click(screen.getByRole('button', {name:'Zoom in'}));
  await waitFor(() => expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,750));
  fireEvent.click(screen.getByRole('button', {name:'Fit page'}));
  await waitFor(() => expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,600));
  fireEvent.wheel(screen.getByTestId('picture-pan'), {ctrlKey:true, deltaY:-100});
  await waitFor(() => expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,750));
  fireEvent.click(screen.getByRole('button', {name:'Zoom out'}));
  await waitFor(() => expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,600));
  fireEvent.click(screen.getByRole('radio', {name:'Text'}));
  await screen.findByText(/ONE read no text|scanned/i);
});

test('opening another file resets text mode to Picture', async () => {
  setLanguage('en');
  const sources = fakeSources({pages:{a:1,b:1}});
  const {rerender} = render(<FileDoc sources={sources} fileId="a" />);
  await screen.findByRole('img');
  fireEvent.click(screen.getByRole('radio',{name:'Text'}));
  rerender(<FileDoc sources={sources} fileId="b" />);
  await waitFor(() => expect(screen.getByRole('radio',{name:'Picture'})).toHaveAttribute('aria-checked','true'));
});

test('pinch requests a sharper page and pointer drag pans the picture', async () => {
  setLanguage('en');
  const sources = fakeSources({pages:{f:1}});
  sources.pageImage = vi.fn(sources.pageImage);
  render(<FileDoc sources={sources} fileId="f" />);
  await screen.findByRole('img');
  const pan = screen.getByTestId('picture-pan');
  fireEvent.pointerDown(pan,{pointerId:1,button:0,clientX:100,clientY:100});
  fireEvent.pointerDown(pan,{pointerId:2,button:0,clientX:200,clientY:100});
  fireEvent.pointerMove(pan,{pointerId:2,clientX:300,clientY:100});
  await waitFor(() => expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,1200));
  fireEvent.pointerUp(pan,{pointerId:2});
  pan.scrollLeft = 100;
  pan.scrollTop = 100;
  fireEvent.pointerMove(pan,{pointerId:1,clientX:80,clientY:70});
  expect(pan.scrollLeft).toBe(120);
  expect(pan.scrollTop).toBe(130);
  fireEvent.pointerCancel(pan,{pointerId:1});
  fireEvent.pointerMove(pan,{pointerId:1,clientX:10,clientY:10});
  expect(pan.scrollLeft).toBe(120);
});

test('zoom respects render bounds and Cmd+wheel, while ordinary wheel scrolls', async () => {
  setLanguage('en');
  const sources = fakeSources({pages:{f:1}});
  sources.pageImage = vi.fn(sources.pageImage);
  render(<FileDoc sources={sources} fileId="f" />);
  await screen.findByRole('img');
  const pan = screen.getByTestId('picture-pan');
  fireEvent.wheel(pan,{deltaY:-100});
  expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,600);
  fireEvent.wheel(pan,{metaKey:true,deltaY:-100});
  await waitFor(() => expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,750));
  for (let i=0;i<12;i++) fireEvent.click(screen.getByRole('button',{name:'Zoom out'}));
  await waitFor(() => expect(sources.pageImage).toHaveBeenLastCalledWith('f',1,200));
  expect(screen.getByRole('button',{name:'Zoom out'})).toBeDisabled();
});
